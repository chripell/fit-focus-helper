#!/usr/bin/env python

import sys
import gi
import numpy as np
import cv2
from astropy.io import fits
from optparse import OptionParser
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GdkPixbuf, Gdk  # nopep8


class Image:

    def __init__(self, widget: Gtk.Widget):
        self.widget = widget

    def load(self, filename: str):
        self.hdul = fits.open(filename)
        self.data = self.hdul[0].data
        self.header = self.hdul[0].header
        self.height = self.data.shape[0]
        self.width = self.data.shape[1]
        self.black = np.iinfo(self.data.dtype).min
        self.white = np.iinfo(self.data.dtype).max
        try:
            self.black = self.header["CBLACK"]
            self.white = self.header["CWHITE"]
        except KeyError:
            pass
        self.bayer = "NONE"
        self.cdata = None
        try:
            self.bayer = self.header["BAYERPAT"]
        except KeyError:
            pass
        if self.bayer == "GRBG":
            # TODO: use numexpr and other bayer
            self.cdata = cv2.cvtColor(self.data, cv2.COLOR_BAYER_GR2RGB)
            img_gray = (0.299 * self.cdata[:, :, 2] +
                        0.587 * self.cdata[:, :, 1] +
                        0.114 * self.cdata[:, :, 0])
            self.data = img_gray.astype("uint16")

    def display(self):
        if self.cdata is None:
            if self.white == 65535 and self.data.dtype.name == "uint16":
                # TODO: use numexpr
                img = self.data // 257
                img = img.astype(np.uint8)
            else:
                print("TODO: slowpath")
            img = np.repeat(img, 3)
        else:
            if self.white == 65535 and self.data.dtype.name == "uint16":
                img = self.cdata // 257
            else:
                print("TODO: slowpath")
        img = img.ravel()
        pixbuf = GdkPixbuf.Pixbuf.new_from_data(
            img, GdkPixbuf.Colorspace.RGB, False, 8,
            self.width, self.height, 3 * self.width)
        self.widget.set_from_pixbuf(pixbuf)


class FocuserApp(Gtk.Window):

    def __init__(self):
        parser = OptionParser(usage="usage: %prog [opts]")
        parser.add_option("--image", type="string", default="",
                          help="Open a single image")
        (self.options, self.args) = parser.parse_args()

    def run(self):
        if self.options.image != "":
            self.single_image(self.options.image)
        else:
            print("You must specify --image or --dir")
            Gtk.main_quit

    def set_status(self, msg: str):
        self.status.remove_all(self.status_id)
        self.status.push(self.status_id, msg)

    def setup(self):
        Gtk.Window.__init__(
            self, title="FIT Focus Helper", *self.args)
        self.main = Gtk.VBox()
        self.add(self.main)
        scroll = Gtk.ScrolledWindow()
        self.image = Gtk.Image()
        scroll.add(self.image)
        self.main.pack_start(scroll, True, True, 0)
        self.status = Gtk.Statusbar()
        self.status_id = self.status.get_context_id("Focuser App")
        self.set_status("Loading...")
        self.main.pack_end(self.status, False, False, 0)
        self.connect("delete-event", Gtk.main_quit)
        self.show_all()

    def single_image(self, filename: str):
        self.img = Image(self.image)
        self.img.load(filename)
        self.img.display()


if __name__ == "__main__":
    app = FocuserApp()
    app.setup()
    app.run()
    Gtk.main()
