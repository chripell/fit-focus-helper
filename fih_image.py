
from astropy.io import fits
import numpy as np
import cv2
import threading
import gi
import cairo
from focuser import Focuser
from typing import Dict, Any, Tuple, Optional
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk


class Image:

    CONV = {
        "GRBG": (cv2.COLOR_BAYER_GR2RGBA, cv2.COLOR_BAYER_GR2RGB),
        "GRBGi": (cv2.COLOR_BAYER_GR2BGRA, cv2.COLOR_BAYER_GR2BGR),
        "RGGB": (cv2.COLOR_BAYER_RG2RGBA, cv2.COLOR_BAYER_RG2RGB),
        "RGGBi": (cv2.COLOR_BAYER_RG2BGRA, cv2.COLOR_BAYER_RG2BGR),
        "BGGR": (cv2.COLOR_BAYER_BG2RGBA, cv2.COLOR_BAYER_BG2RGB),
        "BGGRi": (cv2.COLOR_BAYER_BG2BGRA, cv2.COLOR_BAYER_BG2BGR),
        "GBRG": (cv2.COLOR_BAYER_GB2RGBA, cv2.COLOR_BAYER_GB2RGB),
        "GBRGi": (cv2.COLOR_BAYER_GB2BGRA, cv2.COLOR_BAYER_GB2BGR),
    }

    def __init__(
            self, filename: str, parent: Gtk.Widget):
        self.widget = parent.image
        self.box = parent.scroll
        self.filename = filename
        self.parent = parent
        self.data: Optional[np.ndarray] = None
        self.cdata: Optional[np.ndarray] = None
        self.focuser: Optional[Focuser] = None
        self.percentiles: Dict[int, Tuple[float, float]] = {}
        self.redrawing = False
        self.width = 0
        self.height = 0
        self.black = 0
        self.white = 0
        self.bayer = "NONE"

    def report_error(self, msg: str):
        self.parent.set_status(msg)
        self.parent.broken(self.filename)

    def load(self, param: Dict[str, Any]) -> bool:
        try:
            hdul = fits.open(self.filename)
            self.data = hdul[0].data
            if self.data is None:
                raise ValueError("Empty data from FITS file")
            header = hdul[0].header
            self.height = self.data.shape[0]
            self.width = self.data.shape[1]
        except Exception as e:
            msg = "Cannot load %s: %s" % (self.filename, str(e))
            GLib.idle_add(self.report_error, msg)
            return False
        self.black = np.iinfo(self.data.dtype).min
        self.white = np.iinfo(self.data.dtype).max
        try:
            self.black = header["CBLACK"]
            self.white = header["CWHITE"]
        except KeyError:
            pass
        self.bayer = "NONE"
        self.cdata = None
        try:
            self.bayer = header["BAYERPAT"]
        except KeyError:
            pass
        self.debayer(param)
        return True

    def debayer(self, param):
        if self.bayer == "NONE":
            return
        if param["display/lab"]:
            d = cv2.cvtColor(self.data, self.CONV[self.bayer][1])
            d = d.astype(np.float32) / 65535.0
            self.cdata = cv2.cvtColor(d, cv2.COLOR_RGB2HLS)
        else:
            self.cdata = cv2.cvtColor(self.data, self.CONV[self.bayer][0])
        self.data = None

    def make_gray(self):
        self.data = cv2.cvtColor(self.cdata, cv2.COLOR_RGBA2GRAY)

    def gtk_display(self, surface: cairo.Surface, msg: str, gen: int):
        if self.parent.generation != gen:
            return
        self.redrawing = False
        self.widget.set_from_surface(surface)
        self.parent.set_status(msg)

    def histogram_stretch(
            self, img: np.ndarray, percent: int) -> Tuple[float, float]:
        try:
            return self.percentiles[percent]
        except KeyError:
            if self.data is None:
                self.make_gray()
            want = [0.05, 0.5, 2.5, 5.0, 95.0, 97.5, 99.5, 99.95]
            p = np.percentile(self.data, want)
            self.percentiles = {
                1: (p[0], p[len(want) - 1]),
                10: (p[1], p[len(want) - 2]),
                50: (p[2], p[len(want) - 3]),
                100: (p[3], p[len(want) - 4]),
            }
        return self.percentiles[percent]

    def gamma_stretch(
            self, img: np.ndarray, gamma: float) -> np.ndarray:
        return img ** gamma

    def do_scale(
            self, img: np.ndarray, param: Dict[str, Any]
    ) -> Tuple[np.ndarray, float, int, int]:
        scale = 1
        width = self.width
        height = self.height
        if param["display/scale"]:
            box = self.box.get_allocation()
            scale_w = width / box.width
            scale_h = height / box.height
            if scale_w > scale_h:
                scale = scale_w
            else:
                scale = scale_h
            width = int(width / scale)
            height = int(height / scale)
            if scale > 1:
                interpol = cv2.INTER_AREA
            else:
                interpol = cv2.INTER_LINEAR
            img = cv2.resize(img, (width, height), interpolation=interpol)
        return (img, scale, width, height)

    def do_stretch(
            self, img: np.ndarray, param: Dict[str, Any]
    ) -> np.ndarray:
        cmin = float(self.black)
        cmax = float(self.white)
        if param["display/histogram_stretch_percent"] > 0:
            (cmin, cmax) = self.histogram_stretch(
                img, param["display/histogram_stretch_percent"])
        gamma = param["display/gamma_stretch"]
        if gamma > 0:
            img = self.gamma_stretch(img, gamma)
            cmin = cmin ** gamma
            cmax = cmax ** gamma
        return np.clip((img - cmin) / ((cmax - cmin) / 255.0), 0, 255)

    def do_focuser(
            self, surface: cairo.Surface, param: Dict[str, Any],
            op: str, scale: float):
        if param["focuser/show"] == "nothing":
            return
        cr = cairo.Context(surface)
        if (self.focuser is None or
                op == "new" or op.startswith("focuser/")):
            self.focuser = Focuser(
                algo=param["focuser/finder"],
                n_stars=param["focuser/n_stars"],
                fwhm=param["focuser/fwhm"],
                threshold_stds=param["focuser/threshold"])
            if self.data is None:
                self.make_gray()
            self.focuser.evaluate(self.data)
            if param["focuser/show"] == "hfr":
                self.focuser.hfr(self.data)
        self.focuser.draw(cr, param["focuser/show"], scale=scale,
                          show_text=param["focuser/text"])

    def thread_display(self, param: Dict[str, Any], op: str, gen: int):
        if self.parent.generation != gen:
            return
        if self.data is None and self.cdata is None:
            if not self.load(param):
                return
        if self.parent.generation != gen:
            return
        if param["display/force_gray"] and self.data is None:
            self.make_gray()
        is_gray = self.cdata is None or param["display/force_gray"]
        if is_gray:
            img = self.data
        else:
            img = self.cdata
        if self.parent.generation != gen:
            return
        if img is None:
            self.redrawing = False
            self.parent.set_status("Empty Image")
            return
        (img, scale, width, height) = self.do_scale(img, param)
        if self.parent.generation != gen:
            return
        if param["display/lab"]:
            if not is_gray:
                img = cv2.cvtColor(img, cv2.COLOR_HLS2BGR) * 255
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGRA)
        else:
            img = self.do_stretch(img, param)
        if img is None:
            self.redrawing = False
            self.parent.set_status("Empty Image")
            return
        img = img.astype(np.uint8)
        if param["display/invert"]:
            img = 255 - img
        if self.parent.generation != gen:
            return
        if is_gray:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGBA)
        if self.parent.generation != gen:
            return
        if img is None:
            self.redrawing = False
            self.parent.set_status("Empty Image")
            return
        surface = cairo.ImageSurface.create_for_data(
            img.data, cairo.FORMAT_RGB24, width, height)
        if self.parent.generation != gen:
            return
        self.do_focuser(surface, param, op, scale)
        if self.parent.generation != gen:
            return
        msg = "Loaded %s" % self.filename
        if param["focuser/show"] != "nothing" and self.focuser:
            msg = msg + ", found %d stars" % self.focuser.num()
        GLib.idle_add(self.gtk_display, surface, msg, gen)

    def display(self, param: Dict[str, Any], op: str):
        self.parent.set_status(
            "Loading %s" % self.filename)
        self.parent.generation = self.parent.generation + 1
        thread = threading.Thread(
            target=lambda: self.thread_display(
                param, op, self.parent.generation))
        thread.daemon = True
        thread.start()

    def process(self, param: Dict[str, Any], img, fmt, bayer):
        if self.redrawing:
            return
        self.parent.generation = self.parent.generation + 1
        self.height = img.shape[0]
        self.width = img.shape[1]
        self.black = 0
        if fmt in (0, 2):
            if fmt == 0:
                self.white = 255
            else:
                self.white = 65535
            self.data = img
            self.bayer = bayer
            self.debayer(param)
        elif fmt == 1:
            self.white = 255
            self.cdata = np.stack(
                (img[:, :, 0], img[:, :, 1], img[:, :, 2],
                 np.zeros((self.height, self.width), dtype=np.uint8)),
                axis=2)
            self.data = None
        elif fmt == 3:
            self.white = 255
            self.data = img
            self.cdata = None
        else:
            return
        self.redrawing = True
        thread = threading.Thread(
            target=lambda: self.thread_display(
                param, "new", self.parent.generation))
        thread.daemon = True
        thread.start()
