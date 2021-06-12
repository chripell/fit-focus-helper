
import gi
import pyasicam.pyasicam as pc
from fih_image import Image
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib


class ZwoDialog(Gtk.Dialog):

    def __init__(self, parent, cams):
        Gtk.Dialog.__init__(
            self, title="Select Camera", transient_for=parent, flags=0)
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK)
        self.cam_list = Gtk.ListBox()
        for c in cams:
            r = Gtk.ListBoxRow()
            r.add(Gtk.Label(label=c))
            self.cam_list.add(r)
        box = self.get_content_area()
        box.add(Gtk.Label(label="Select Camera:"))
        box.add(self.cam_list)
        self.show_all()


def list_zwo_cams(parent):
    cams = []
    n = pc.GetNumOfConnectedCameras()
    for i in range(n):
        c = pc.Camera(i)
        prop = c.GetCameraProperty()
        cams.append("%d: %s" % (i, prop.Name.decode("utf-8")))
    dialog = ZwoDialog(parent, cams)
    response = dialog.run()
    ret = None
    if response == Gtk.ResponseType.OK:
        ret = dialog.cam_list.get_selected_row().get_index()
    dialog.destroy()
    return ret


class ControlsDialog(Gtk.Dialog):

    def __init__(self, parent, cam):
        self.parent = parent
        self.cam = cam
        Gtk.Dialog.__init__(self,
                            title="Camera Parameters",
                            parent=parent,
                            flags=0)
        self.connect('delete-event', self.on_destroy)
        # Avoid maximization by Awesome.
        self.set_role("pop-up")
        self.cam_grid = Gtk.Grid()
        row = 0

        self.cam_mode = Gtk.ListBox()
        self.cam_mode_rows = []
        for i, c in enumerate(("RAW8", "RGB24", "RAW16", "Y8")):
            r = Gtk.ListBoxRow()
            r.add(Gtk.Label(label=c))
            self.cam_mode.add(r)
            self.cam_mode_rows.append(r)
        self.cam_grid.attach(Gtk.Label("Mode:"), 0, row, 1, 1)
        self.cam_grid.attach(self.cam_mode, 1, row, 1, 1)
        row += 1

        self.cam_expo = Gtk.Entry()
        self.cam_expo.set_width_chars(7)
        self.cam_expo.set_hexpand(True)
        self.cam_expo.set_vexpand(True)
        self.cam_grid.attach(Gtk.Label("Exposure (ms):"), 0, row, 1, 1)
        self.cam_grid.attach(self.cam_expo, 1, row, 1, 1)
        row += 1

        self.cam_gain = Gtk.Entry()
        self.cam_grid.attach(Gtk.Label("Gain:"), 0, row, 1, 1)
        self.cam_grid.attach(self.cam_gain, 1, row, 1, 1)
        row += 1

        self.cam_brightness = Gtk.Entry()
        self.cam_grid.attach(Gtk.Label("Brightness:"), 0, row, 1, 1)
        self.cam_grid.attach(self.cam_brightness, 1, row, 1, 1)
        row += 1

        self.cam_cooler = Gtk.CheckButton()
        self.cam_grid.attach(Gtk.Label("Cooler:"), 0, row, 1, 1)
        self.cam_grid.attach(self.cam_cooler, 1, row, 1, 1)
        row += 1

        self.cam_temp = Gtk.Entry()
        self.cam_grid.attach(Gtk.Label("Target T:"), 0, row, 1, 1)
        self.cam_grid.attach(self.cam_temp, 1, row, 1, 1)
        row += 1

        self.cam_bin = Gtk.Entry()
        self.cam_grid.attach(Gtk.Label("Bin:"), 0, row, 1, 1)
        self.cam_grid.attach(self.cam_bin, 1, row, 1, 1)
        row += 1

        apply_button = Gtk.Button.new_with_label("Apply")
        apply_button.connect("clicked", self.apply_controls)
        self.cam_grid.attach(apply_button, 0, row, 2, 1)
        row += 1

        close_button = Gtk.Button.new_with_label("Close")
        close_button.connect("clicked", lambda w: self.hide())
        self.cam_grid.attach(close_button, 0, row, 2, 1)
        row += 1

        box = self.get_content_area()
        box.add(self.cam_grid)
        self.show_all()

    def update_controls(self):
        self.cam.get_controls()
        for i, _ in enumerate(("RAW8", "RGB24", "RAW16", "Y8")):
            if i == self.parent.param["cam/mode"]:
                self.cam_mode.select_row(
                    self.cam_mode_rows[i])
        self.cam_expo.set_text(str(self.parent.param["cam/expo_us"]//1000))
        self.cam_gain.set_text(str(self.parent.param["cam/gain"]))
        self.cam_brightness.set_text(str(self.parent.param["cam/brightness"]))
        self.cam_cooler.set_active(self.parent.param["cam/cooler"])
        self.cam_temp.set_text(str(self.parent.param["cam/temp"]))
        self.cam_bin.set_text(str(self.parent.param["cam/bin"]))

    def apply_controls(self, w):
        try:
            row = self.cam_mode.get_selected_row()
            idx = row.get_index()
            self.parent.param["cam/mode"] = idx
            self.parent.param["cam/expo_us"] = int(
                self.cam_expo.get_text()) * 1000
            self.parent.param["cam/gain"] = int(
                self.cam_gain.get_text())
            self.parent.param["cam/brightness"] = int(
                self.cam_brightness.get_text())
            self.parent.param["cam/cooler"] = self.cam_cooler.get_active()
            self.parent.param["cam/temp"] = int(self.cam_temp.get_text())
            self.parent.param["cam/bin"] = int(self.cam_bin.get_text())
            self.cam.new_par = True
        except ValueError:
            self.update_controls()

    def on_destroy(self, w, d):
        self.hide()
        return True


class Cam:

    def __init__(self, parent):
        self.parent = parent
        self.parent.set_status("Stopped")
        self.typ = parent.param["cam/type"]
        if self.typ == "zwo":
            pc.GetNumOfConnectedCameras()
            self.c = pc.Camera(int(parent.param["cam/id"]))
            self.prop = self.c.GetCameraProperty()
            self.is_color = self.prop.IsColorCam == 1
            self.name = self.prop.Name.decode()
            if self.is_color:
                if self.name == "ZWO ASI120MC":
                    self.bayer = "RGGBi"
                else:
                    self.bayer = "GRBG"
            else:
                self.bayer = "NONE"
            self.c.OpenCamera()
            self.c.InitCamera()
        self.new_par = False
        self.controls_dialog = None
        self.image = None

    def close(self):
        if self.typ == "zwo":
            self.c.CloseCamera()

    def start(self):
        self.update()
        if self.typ == "zwo":
            self.parent.set_status("Exposing")
            self.c.StartExposure(0)
        self.parent.param["cam/run"] = True
        GLib.timeout_add(100, self.poll)

    def stop(self):
        if not self.parent.param["cam/run"]:
            return
        self.parent.param["cam/run"] = False
        if self.typ == "zwo":
            self.parent.set_status("Stopped")
            self.c.StopExposure()

    def poll(self):
        if not self.parent.param["cam/run"]:
            return False
        if self.typ == "zwo":
            failed = False
            st = self.c.GetExpStatus()
            if st == pc.EXP_IDLE:
                print("Internal Error: Callback while no exposure")
                return False
            elif st == pc.EXP_WORKING:
                return True
            elif st == pc.EXP_FAILED:
                print("Exposure failed!")
                failed = True
            if st == pc.EXP_SUCCESS:
                im = self.c.GetDataAfterExp()
                if not self.image or not self.image.redrawing:
                    self.image = Image("", self.parent)
                    self.image.process(
                        self.parent.param, im, self.cam_mode, self.bayer)
            if self.new_par:
                self.update()
                self.new_par = False
            self.c.StartExposure(0)
            if failed:
                self.parent.set_status("Exposing after failure")
            else:
                self.parent.set_status("Exposing")
        return True

    def update(self):
        if self.typ == "zwo":
            caps = self.c.GetCameraProperty()
            self.cam_mode = self.parent.param["cam/mode"]
            ok = True
            try:
                self.c.SetROIFormat(
                    caps.MaxWidth, caps.MaxHeight,
                    self.parent.param["cam/bin"],
                    self.parent.param["cam/mode"])
            except pc.Error:
                ok = False
            try:
                self.c.SetControlValue(
                    pc.EXPOSURE, self.parent.param["cam/expo_us"], False)
            except pc.Error:
                ok = False
            try:
                self.c.SetControlValue(
                    pc.GAIN, self.parent.param["cam/gain"], False)
            except pc.Error:
                ok = False
            try:
                self.c.SetControlValue(
                    pc.BRIGHTNESS, self.parent.param["cam/brightness"], False)
            except pc.Error:
                ok = False
            try:
                self.c.SetControlValue(
                    pc.COOLER_ON, self.parent.param["cam/cooler"], False)
            except pc.Error:
                pass
            else:
                try:
                    self.c.SetControlValue(
                        pc.TARGET_TEMP, self.parent.param["cam/temp"], False)
                except pc.Error:
                    ok = False
            if not ok and self.controls_dialog:
                self.controls_dialog.update_controls()

    def controls(self):
        if not self.controls_dialog:
            self.controls_dialog = ControlsDialog(self.parent, self)
        self.controls_dialog.update_controls()
        self.controls_dialog.show()

    def get_controls(self):
        (_, _,
         self.parent.param["cam/bin"],
         self.parent.param["cam/mode"]) = self.c.GetROIFormat()
        self.parent.param["cam/expo_us"] = self.c.GetControlValue(
            pc.EXPOSURE)[0]
        self.parent.param["cam/gain"] = self.c.GetControlValue(pc.GAIN)[0]
        self.parent.param["cam/brightness"] = self.c.GetControlValue(
            pc.BRIGHTNESS)[0]
        try:
            self.parent.param["cam/cooler"] = self.c.GetControlValue(
                pc.COOLER_ON)[0] != 0
            self.parent.param["cam/temp"] = self.c.GetControlValue(
                pc.TARGET_TEMP)[0]
        except pc.Error:
            pass
