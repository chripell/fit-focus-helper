#!/usr/bin/env python
"""
Copyright 2021 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import json
import os
from pathlib import Path
from optparse import OptionParser
from fih_image import Image
from fih_cmd import ImagerCmd
from fih_cam import Cam
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib


class ImagerApp(Gtk.Window):

    def __init__(self):
        parser = OptionParser(usage="usage: %prog [opts]")
        parser.add_option("--image", type="string", default="",
                          help="Open a single image")
        parser.add_option("--dir", type="string", default="",
                          help="Open a directory")
        parser.add_option("--config", type="string", default="",
                          help="Use config file")
        parser.add_option("--zwo_camera", type="string", default="",
                          help="Open the given number ZWO camera")
        (self.options, self.args) = parser.parse_args()
        self.img = None
        self.dire = None
        self.current = None
        self.fit_files = None
        self.do_reload = False
        self.timer = None
        self.generation = 0
        self.file_list_rows = []
        self.cam = None
        self.indi = None
        self.param = {
            "display/scale": True,
            "display/invert": False,
            "display/histogram_stretch_percent": 0,
            "display/gamma_stretch": 0,
            "display/force_gray": False,
            "display/lab": False,
            "multi/sort_timestamp": False,
            "focuser/finder": "dao",
            "focuser/show": "nothing",
            "focuser/n_stars": 100,
            "focuser/text": False,
            "focuser/fwhm": 3.0,
            "focuser/threshold": 3.0,
            "cam/type": "none",
            "cam/id": 0,
            "cam/run": False,
            "cam/save": False,
            "cam/prefix": os.path.join(Path.home(), "Capture"),
            "cam/expo_us": 100000,
            "cam/gain": 50,
            "cam/brightness": 50,
            "cam/cooler": False,
            "cam/temp": 0,
            "cam/mode": 0,
            "cam/bin": 1,
            "indi/hostname": "localhost",
            "indi/port": 7624,
            "indi/match_telescope": "Telescope Simulator|SynScan",
            "indi/keys": True,
        }

    def run(self):
        if self.options.image != "":
            GLib.timeout_add(500, self.single_image, self.options.image)
        elif self.options.dir != "":
            GLib.timeout_add(500, self.multi_image, self.options.dir)
        elif self.options.config != "":
            GLib.timeout_add(500, self.load_conf, self.options.config)
        elif self.options.zwo_camera != "":
            GLib.timeout_add(
                500, self.open_cam, "zwo", self.options.zwo_camera)

    def set_status(self, msg: str):
        self.status.remove_all(self.status_id)
        if self.current is not None:
            msg = "(%d/%d) %s" % (self.current + 1, len(self.fit_files), msg)
        self.status.push(self.status_id, msg)

    def write_status(self, msg: str):
        self.status.remove_all(self.status_id)
        self.status.push(self.status_id, msg)

    def setup(self):
        Gtk.Window.__init__(
            self, title="FIT Focus Helper", *self.args)
        self.main = Gtk.VBox()
        self.add(self.main)
        self.menu = ImagerCmd(self)
        self.main.pack_start(self.menu, False, False, 0)
        self.scroll = Gtk.ScrolledWindow()
        self.image = Gtk.Image()
        self.scroll.add(self.image)
        self.paned = Gtk.HPaned()
        self.scroll_list = Gtk.ScrolledWindow()
        self.file_list = Gtk.ListBox()
        self.scroll_list.add(self.file_list)
        self.paned.add1(self.scroll_list)
        self.paned.add2(self.scroll)
        self.main.pack_start(self.paned, True, True, 0)
        self.paned.set_position(0)
        self.param["mode"] = "empty"
        self.status = Gtk.Statusbar()
        self.status_id = self.status.get_context_id("Imager App")
        self.set_status("No Image")
        self.main.pack_end(self.status, False, False, 0)
        self.connect("delete-event", Gtk.main_quit)
        self.menu.hook_keys()
        self.show_all()

    def clear_file_list(self):
        for row in self.file_list_rows:
            self.file_list.remove(row)
        self.file_list_rows = []

    def clear_multi(self):
        self.dire = None
        self.current = None
        self.fit_files = None
        self.paned.set_position(0)
        self.clear_file_list()

    def single_image(self, filename: str):
        self.param["target"] = filename
        self.clear_multi()
        self.stop_cam()
        self.image.clear()
        self.param["mode"] = "single"
        self.img = Image(filename, self)
        self.img.display(self.param, "new")

    def scroll_list_box(self):
        row = self.file_list.get_selected_row()
        if not row:
            return
        dx, dy = row.translate_coordinates(self.file_list, 0, 0)
        adj = self.file_list.get_adjustment()
        if not adj:
            return
        rw, rh = row.get_preferred_height()
        adj.set_value(dy - (adj.get_page_size() - rh) / 2)

    def show_img(self, what: int):
        if self.fit_files is None:
            return
        ll = len(self.fit_files)
        if ll == 0:
            return
        force = False
        if what == ImagerCmd.IMG_LAST:
            what = ll - 1
        elif what == ImagerCmd.IMG_NEXT and self.current is not None:
            what = self.current + 1
        elif what == ImagerCmd.IMG_PREV and self.current is not None:
            what = self.current - 1
        elif what == ImagerCmd.IMG_REDRAW:
            if not self.current:
                return
            force = True
            what = self.current
        if what >= ll:
            what = ll - 1
        if what < 0:
            what = 0
        if what == self.current and not force:
            return
        self.file_list.select_row(self.file_list_rows[what])
        self.current = what
        self.img = Image(self.fit_files[self.current][0], self)
        self.img.display(self.param, "new")
        GLib.idle_add(self.scroll_list_box)

    def add_to_file_list(self, dire: str) -> bool:
        fit_files1 = [os.path.join(dire, f) for f in os.listdir(dire) if (
            os.path.isfile(os.path.join(dire, f)) and
            os.path.splitext(f)[1].lower() == ".fit")]
        fit_files = [(f, os.path.getmtime(f)) for f in fit_files1]
        key = 0
        if self.param["multi/sort_timestamp"]:
            key = 1
        fit_files.sort(key=lambda x: x[key])
        if self.fit_files == fit_files:
            return False
        self.clear_file_list()
        for f, tstamp in fit_files:
            row = Gtk.ListBoxRow()
            b = os.path.basename(f)
            row.add(Gtk.Label(label=b))
            self.file_list.add(row)
            self.file_list_rows.append(row)
        self.fit_files = fit_files
        return True

    def multi_image(self, dire: str):
        self.param["target"] = dire
        self.param["mode"] = "multi"
        self.stop_cam()
        if not self.add_to_file_list(dire):
            return
        self.image.clear()
        self.show_all()
        self.write_status("")
        self.file_list.connect(
            "row-activated",
            lambda l, r: self.show_img(r.get_index()))
        self.dire = dire
        pmin, _ = self.file_list.get_preferred_width()
        if not pmin:
            pmin = 200
        self.paned.set_position(pmin)
        self.show_img(ImagerCmd.IMG_LAST)
        self.paned.connect(
            "notify::position",
            lambda w, u: self.show_img(ImagerCmd.IMG_REDRAW))

    def multi_reload(self):
        if self.dire is None:
            return
        self.multi_image(self.dire)

    def set_param(self, par: str, val):
        self.param[par] = val
        if self.img is None:
            return
        if not self.cam:
            self.img.display(self.param, par)

    def get_param(self, par: str):
        return self.param[par]

    def broken(self, filename: str):
        self.image.clear()

    def auto_reload(self, state):
        self.do_reload = state
        if not state:
            if self.timer is not None:
                GLib.source_remove(self.timer)
                self.timer = None
            return
        self.timer = GLib.timeout_add_seconds(1, self.timer_tick)

    def timer_tick(self):
        if self.do_reload is None:
            return False
        self.multi_reload()
        return True

    def save_conf(self, fname: str):
        with open(fname, "w") as f:
            json.dump(self.param, f)

    def load_conf(self, fname: str):
        with open(fname, "r") as f:
            new_param = json.load(f)
            if self.param["mode"] != "empty":
                try:
                    del new_param["target"]
                    del new_param["mode"]
                except KeyError:
                    pass
            self.param.update(new_param)
        self.menu.update_ui(self.param)
        if self.param["mode"] == "single":
            self.single_image(self.param["target"])
        elif self.param["mode"] == "multi":
            self.multi_image(self.param["target"])

    def open_cam(self, typ: str, ident: str):
        self.param["cam/type"] = typ
        self.param["cam/id"] = ident
        self.clear_multi()
        self.image.clear()
        self.param["mode"] = "cam"
        self.cam = Cam(self)

    def stop_cam(self):
        self.param["cam/run"] = False
        self.menu.update_ui(self.param)
        if self.cam:
            self.cam.stop()
            self.cam.close()
            self.cam = None


if __name__ == "__main__":
    app = ImagerApp()
    app.setup()
    app.run()
    Gtk.main()
