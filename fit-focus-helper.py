#!/usr/bin/env python

import numpy as np
import cv2
import threading
import os
from astropy.io import fits
from optparse import OptionParser
from typing import Dict, Any, Tuple
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GdkPixbuf, GLib  # nopep8


class Image:

    def __init__(
            self, filename: str, parent: Gtk.Widget):
        self.widget = parent.image
        self.box = parent.scroll
        self.filename = filename
        self.parent = parent
        self.data = None
        self.cdata = None
        self.percentiles: Dict[int, Tuple[float, float]] = {}

    def report_error(self, msg: str):
        self.parent.set_status(msg)
        self.parent.broken(self.filename)

    def load(self) -> bool:
        try:
            hdul = fits.open(self.filename)
            self.data = hdul[0].data
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
        if self.bayer == "GRBG":
            # TODO: other bayer
            self.cdata = cv2.cvtColor(self.data, cv2.COLOR_BAYER_GR2RGB)
            self.data = None
        return True

    def make_gray(self):
        self.data = (0.299 * self.cdata[:, :, 2] +
                     0.587 * self.cdata[:, :, 1] +
                     0.114 * self.cdata[:, :, 0])

    def gtk_display(self, pixbuf: GdkPixbuf.Pixbuf, msg: str):
        self.widget.set_from_pixbuf(pixbuf)
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

    def thread_display(self, param: Dict[str, Any], op: str):
        if self.data is None and self.cdata is None:
            if not self.load():
                return
        if param["display/force_gray"] and self.data is None:
            self.make_gray()
        is_gray = self.cdata is None or param["display/force_gray"]
        if is_gray:
            img = self.data
        else:
            img = self.cdata
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
        cmin = self.black
        cmax = self.white
        if param["display/histogram_stretch_percent"] > 0:
            (cmin, cmax) = self.histogram_stretch(
                img, param["display/histogram_stretch_percent"])
        gamma = param["display/gamma_stretch"]
        if gamma > 0:
            img = self.gamma_stretch(img, gamma)
            cmin = cmin ** gamma
            cmax = cmax ** gamma
        img = np.clip((img - cmin) / ((cmax - cmin) / 255.0), 0, 255)
        img = img.astype(np.uint8)
        if param["display/invert"]:
            img = 255 - img
        if is_gray:
            img = np.repeat(img, 3)
        img = img.ravel()
        pixbuf = GdkPixbuf.Pixbuf.new_from_data(
            img, GdkPixbuf.Colorspace.RGB, False, 8,
            width, height, 3 * width)
        GLib.idle_add(self.gtk_display, pixbuf,
                      "Loaded %s" % self.filename)

    def display(self, param: Dict[str, Any], op: str):
        self.parent.set_status(
            "Loading %s" % self.filename)
        thread = threading.Thread(
            target=lambda: self.thread_display(param, op))
        thread.daemon = True
        thread.start()


class FocuserCmd(Gtk.MenuBar):

    def add_sub_menu(self, name):
        sub = Gtk.MenuItem.new_with_mnemonic(name)
        self.append(sub)
        menu = Gtk.Menu()
        sub.set_submenu(menu)
        return menu

    def add_entry(self, menu, name, command):
        item = Gtk.MenuItem(label=name)
        item.connect("activate", command)
        menu.append(item)

    def add_check(self, menu, name, command, on=False):
        item = Gtk.CheckMenuItem(label=name)
        if on:
            item.set_active(True)
        item.connect("activate", command)
        menu.append(item)

    def add_radio(self, menu, group, name, command, active):
        item = Gtk.RadioMenuItem(
            label=name, group=self._groups.get(group, None))
        self._groups[group] = item
        item.connect("activate", command)
        if active:
            item.set_active(active)
        menu.append(item)

    def add_separator(self, menu):
        menu.append(Gtk.SeparatorMenuItem())

    def __init__(self, parent):
        self.p = parent
        Gtk.MenuBar.__init__(self)
        self._groups = {}
        file_menu = self.add_sub_menu("_File")
        self.add_entry(
            file_menu, "Open Picture", self.open_picture)
        self.add_entry(
            file_menu, "Open Directory", self.open_directory)
        self.add_separator(file_menu)
        self.add_entry(
            file_menu, "Exit", self.exit_app)
        view_menu = self.add_sub_menu("_View")
        self.add_check(
            view_menu, "Force Gray", self.force_gray)
        self.add_check(
            view_menu, "Gamma Stretch", self.gamma_stretch)
        self.add_check(
            view_menu, "Zoom to fit", self.scale, True)
        self.add_check(
            view_menu, "Invert", self.invert, False)
        self.add_separator(view_menu)
        self.add_radio(
            view_menu, 'histogram_stretch', "No histogram stretch",
            self.histo_0, True)
        self.add_radio(
            view_menu, 'histogram_stretch', "Histogram stretch 0.1%",
            self.histo_01, False)
        self.add_radio(
            view_menu, 'histogram_stretch', "Histogram stretch 1%",
            self.histo_1, False)
        self.add_radio(
            view_menu, 'histogram_stretch', "Histogram stretch 5%",
            self.histo_5, False)
        self.add_radio(
            view_menu, 'histogram_stretch', "Histogram stretch 10%",
            self.histo_10, False)
        nav_menu = self.add_sub_menu("_Navigate")
        self.add_entry(
            nav_menu, "Reload List", self.multi_reload)
        self.add_entry(
            nav_menu, "First Image", self.first_img)
        self.add_entry(
            nav_menu, "Previous Image", self.prev_img)
        self.add_entry(
            nav_menu, "Next Image", self.next_img)
        self.add_entry(
            nav_menu, "Last Image", self.last_img)
        self.add_check(
            nav_menu, "Sort by date", self.sort_by_date, False)

    def open_picture(self, w):
        dialog = Gtk.FileChooserDialog(
            title="Please choose a Fit image",
            parent=self.p, action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,
            Gtk.ResponseType.OK,
        )
        filter_fit = Gtk.FileFilter()
        filter_fit.set_name("Fit images")
        filter_fit.add_pattern("*.fit")
        filter_fit.add_pattern("*.FIT")
        dialog.add_filter(filter_fit)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.p.single_image(dialog.get_filename())
        dialog.destroy()

    def open_directory(self, w):
        dialog = Gtk.FileChooserDialog(
            title="Please choose a directory with fit images",
            parent=self.p, action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,
            Gtk.ResponseType.OK,
        )
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.p.multi_image(dialog.get_filename())
        dialog.destroy()

    def exit_app(self, w):
        Gtk.main_quit()

    def force_gray(self, w):
        self.p.set_param("display/force_gray", w.get_active())

    def invert(self, w):
        self.p.set_param("display/invert", w.get_active())

    def gamma_stretch(self, w):
        if w.get_active():
            self.p.set_param("display/gamma_stretch", 1.0 / 2.2)
        else:
            self.p.set_param("display/gamma_stretch", 0)

    def histo_0(self, w):
        if w.get_active():
            self.p.set_param("display/histogram_stretch_percent", 0)

    def histo_01(self, w):
        if w.get_active():
            self.p.set_param("display/histogram_stretch_percent", 1)

    def histo_1(self, w):
        if w.get_active():
            self.p.set_param("display/histogram_stretch_percent", 10)

    def histo_5(self, w):
        if w.get_active():
            self.p.set_param("display/histogram_stretch_percent", 50)

    def histo_10(self, w):
        if w.get_active():
            self.p.set_param("display/histogram_stretch_percent", 100)

    def scale(self, w):
        self.p.set_param("display/scale", w.get_active())

    def first_img(self, w):
        self.p.show_img(FocuserApp.IMG_FIRST)

    def last_img(self, w):
        self.p.show_img(FocuserApp.IMG_LAST)

    def next_img(self, w):
        self.p.show_img(FocuserApp.IMG_NEXT)

    def prev_img(self, w):
        self.p.show_img(FocuserApp.IMG_PREV)

    def multi_reload(self, w):
        self.p.multi_reload()

    def sort_by_date(self, w):
        self.p.set_param("multi/sort_timestamp", w.get_active())
        self.p.multi_reload()


class FocuserApp(Gtk.Window):

    IMG_FIRST = 0
    IMG_LAST = -1
    IMG_NEXT = -2
    IMG_PREV = -3

    def __init__(self):
        parser = OptionParser(usage="usage: %prog [opts]")
        parser.add_option("--image", type="string", default="",
                          help="Open a single image")
        parser.add_option("--dir", type="string", default="",
                          help="Open a directory")
        (self.options, self.args) = parser.parse_args()
        self.img = None
        self.dire = None
        self.current = None
        self.fit_files = None
        self.param = {
            "display/scale": True,
            "display/invert": False,
            "display/histogram_stretch_percent": 0,
            "display/gamma_stretch": 0,
            "display/force_gray": False,
            "multi/sort_timestamp": False,
        }

    def run(self):
        if self.options.image != "":
            GLib.timeout_add(500, self.single_image, self.options.image)
        elif self.options.dir != "":
            GLib.timeout_add(500, self.multi_image, self.options.dir)

    def set_status(self, msg: str):
        self.status.remove_all(self.status_id)
        if self.current is not None:
            msg = "(%d/%d) %s" % (self.current + 1, len(self.fit_files), msg)
        self.status.push(self.status_id, msg)

    def setup(self):
        Gtk.Window.__init__(
            self, title="FIT Focus Helper", *self.args)
        self.main = Gtk.VBox()
        self.add(self.main)
        menu = FocuserCmd(self)
        self.main.pack_start(menu, False, False, 0)
        self.scroll = Gtk.ScrolledWindow()
        self.image = Gtk.Image()
        self.scroll.add(self.image)
        self.main.pack_start(self.scroll, True, True, 0)
        self.status = Gtk.Statusbar()
        self.status_id = self.status.get_context_id("Focuser App")
        self.set_status("No Image")
        self.main.pack_end(self.status, False, False, 0)
        self.connect("delete-event", Gtk.main_quit)
        self.show_all()

    def single_image(self, filename: str):
        self.dire = None
        self.current = None
        self.fit_files = None
        self.img = Image(filename, self)
        self.img.display(self.param, "new")

    def show_img(self, what: int):
        if self.fit_files is None:
            return
        ll = len(self.fit_files)
        if ll == 0:
            return
        if what == self.IMG_LAST:
            what = ll - 1
        elif what == self.IMG_NEXT and self.current is not None:
            what = self.current + 1
        elif what == self.IMG_PREV and self.current is not None:
            what = self.current - 1
        if what >= ll:
            what = ll - 1
        if what < 0:
            what = 0
        if what == self.current:
            return
        self.current = what
        self.img = Image(self.fit_files[self.current][0], self)
        self.img.display(self.param, "new")

    def multi_image(self, dire: str):
        fit_files1 = [os.path.join(dire, f) for f in os.listdir(dire) if (
            os.path.isfile(os.path.join(dire, f)) and
            os.path.splitext(f)[1].lower() == ".fit")]
        fit_files = [(f, os.path.getmtime(f)) for f in fit_files1]
        key = 0
        if self.param["multi/sort_timestamp"]:
            key = 1
        fit_files.sort(key=lambda x: x[key])
        if self.fit_files == fit_files:
            return
        self.fit_files = fit_files
        self.dire = dire
        self.show_img(self.IMG_LAST)

    def multi_reload(self):
        if self.dire is None:
            return
        self.multi_image(self.dire)

    def set_param(self, par: str, val):
        if self.img is None:
            return
        self.param[par] = val
        self.img.display(self.param, par)

    def broken(self, filename: str):
        if self.fit_files is None:
            return
        for (i, el) in self.fit_files:
            if el[1] == filename:
                del self.fit_files[i]
                break
        self.show_img(self.IMG_LAST)


if __name__ == "__main__":
    app = FocuserApp()
    app.setup()
    app.run()
    Gtk.main()
