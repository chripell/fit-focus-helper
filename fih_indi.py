import PyIndi
import gi
import time
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib


def format_degree(v: float) -> str:
    hh = int(v)
    res = v - hh
    mm = int(res * 60.0)
    res -= mm / 60.0
    ss = int(res * 60.0 * 60.0)
    return f"{hh}:{mm:02d}:{ss:02d}"


class IndiClient(PyIndi.BaseClient):

    def __init__(self, parent, main):
        super(IndiClient, self).__init__()
        self.verbose = False
        self.main = main
        self.parent = parent

    def newDevice(self, d):
        if self.verbose:
            print("INDI: new device " + d.getDeviceName())
        match_telescope = [
            i.strip() for i in
            self.parent.param["indi/match_telescope"].split("|")]
        t = d.getDeviceName()
        if t in match_telescope:
            self.main.telescope = t
            self.main.telescope_obj = d

    def newProperty(self, p):
        if self.verbose:
            print("INDI: new property " + p.getName() +
                  " for device " + p.getDeviceName())

    def removeProperty(self, p):
        if self.verbose:
            print("INDI: remove property " + p.getName() +
                  " for device " + p.getDeviceName())

    def newBLOB(self, bp):
        if self.verbose:
            print("INDI: new BLOB " + bp.name.decode())

    def newSwitch(self, svp):
        if self.verbose:
            print("INDI: new Switch " + svp.name +
                  " for device " + svp.device)

    def newNumber(self, nvp):
        if self.verbose:
            print("INDI: new Number " + nvp.name +
                  " for device " + nvp.device)
        if nvp.name == "EQUATORIAL_EOD_COORD":
            self.main.ra = nvp[0].value
            self.main.dec = nvp[1].value

    def newText(self, tvp):
        if self.verbose:
            print("INDI: new Text " + tvp.name +
                  " for device " + tvp.device)

    def newLight(self, lvp):
        if self.verbose:
            print("INDI: new Light " + lvp.name +
                  " for device " + lvp.device)

    def newMessage(self, d, m):
        if self.verbose:
            print("INDI: new Message " + d.messageQueue(m))

    def serverConnected(self):
        if self.verbose:
            print("INDI: Server connected (" +
                  self.getHost() + ":" + str(self.getPort()) + ")")
        self.main.connected = True

    def serverDisconnected(self, code):
        if self.verbose:
            print("INDI: Server disconnected (exit code = " +
                  str(code) + "," + str(self.getHost()) +
                  ":" + str(self.getPort()) + ")")


class IndiDialog(Gtk.Dialog):

    def __init__(self, parent, client, main):
        self.parent = parent
        self.client = client
        self.main = main
        Gtk.Dialog.__init__(self,
                            title="INDI Dialog",
                            parent=parent,
                            flags=0)
        self.connect('delete-event', self.on_destroy)
        # Avoid maximization by Awesome.
        self.set_role("pop-up")
        self.indi_grid = Gtk.Grid()
        row = 0

        self.hostname = Gtk.Entry()
        self.hostname.set_width_chars(40)
        self.hostname.set_hexpand(True)
        self.hostname.set_vexpand(True)
        self.indi_grid.attach(Gtk.Label("Hostname:"), 0, row, 1, 1)
        self.indi_grid.attach(self.hostname, 1, row, 1, 1)
        row += 1

        self.port = Gtk.Entry()
        self.port.set_hexpand(True)
        self.port.set_vexpand(True)
        self.indi_grid.attach(Gtk.Label("Port:"), 0, row, 1, 1)
        self.indi_grid.attach(self.port, 1, row, 1, 1)
        row += 1

        self.match_telescope = Gtk.Entry()
        self.match_telescope.set_text("Telescope Simulator|SynScan")
        self.match_telescope.set_hexpand(True)
        self.match_telescope.set_vexpand(True)
        self.indi_grid.attach(Gtk.Label("Match_Telescope:"), 0, row, 1, 1)
        self.indi_grid.attach(self.match_telescope, 1, row, 1, 1)
        row += 1

        self.status = Gtk.Label("Not Connected")
        self.status.set_justify(Gtk.Justification.CENTER)
        self.status.set_hexpand(True)
        self.status.set_vexpand(True)
        self.indi_grid.attach(self.status, 0, row, 2, 1)
        row += 1

        connect_button = Gtk.Button.new_with_label("Connect")
        connect_button.connect("clicked", self.connect_indi)
        self.indi_grid.attach(connect_button, 0, row, 2, 1)
        row += 1

        close_button = Gtk.Button.new_with_label("Close")
        close_button.connect("clicked", lambda w: self.hide())
        self.indi_grid.attach(close_button, 0, row, 2, 1)
        row += 1

        box = self.get_content_area()
        box.add(self.indi_grid)
        self.show_all()

    def connect_indi(self, w):
        self.parent.param["indi/hostname"] = self.hostname.get_text()
        try:
            self.parent.param["indi/port"] = int(self.port.get_text())
        except TypeError:
            self.parent.param["indi/port"] = 7624
        self.update_controls()
        self.main.do_connect()

    def on_destroy(self, w, d):
        self.hide()
        return True

    def update_controls(self):
        self.hostname.set_text(
            self.parent.param["indi/hostname"])
        self.port.set_text(
            f"{self.parent.param['indi/port']}")
        self.match_telescope.set_text(
            self.parent.param["indi/match_telescope"])

    def update_ui(self):
        if self.main.errored:
            self.status.set_text(self.main.errored)
            return
        if not self.main.connected:
            self.status.set_text("Not Connected")
            return
        if not self.main.telescope:
            self.status.set_text("No telescope found")
        ra = format_degree(self.main.ra)
        dec = format_degree(self.main.dec)
        self.status.set_text(
            f"Found: {self.main.telescope}\n"
            f"RA={ra} "
            f"Dec={dec}")


class Indi:

    def __init__(self, parent):
        self.parent = parent
        self.client = IndiClient(parent, self)
        self.connected = False
        self.busy = None
        self.controls_dialog = None
        self.telescope = None
        self.telescope_obj = None
        self.errored = None
        self.ra = 0
        self.dec = 0
        GLib.timeout_add(1000, self.periodic)

    def show_dialog(self):
        if not self.controls_dialog:
            self.controls_dialog = IndiDialog(self.parent, self.client, self)
        self.controls_dialog.update_controls()
        self.controls_dialog.show()

    def key_press(self, val):
        if not self.telescope:
            return
        if val == 4 or val == 6:
            sw = self.get_switch("TELESCOPE_MOTION_WE")
            if val == 4:
                sw[0].s = PyIndi.ISS_ON
                sw[1].s = PyIndi.ISS_OFF
            else:
                sw[1].s = PyIndi.ISS_ON
                sw[0].s = PyIndi.ISS_OFF
            self.client.sendNewSwitch(sw)
        if val == 2 or val == 8:
            sw = self.get_switch("TELESCOPE_MOTION_NS")
            if val == 8:
                sw[0].s = PyIndi.ISS_ON
                sw[1].s = PyIndi.ISS_OFF
            else:
                sw[1].s = PyIndi.ISS_ON
                sw[0].s = PyIndi.ISS_OFF
            self.client.sendNewSwitch(sw)
        if val in (1, 3, 7, 9):
            sw = self.get_switch("TELESCOPE_SLEW_RATE")
            idx = (0, 0, 0, 1, 0, 0, 0, 2, 0, 3)[val]
            for i in range(4):
                if i == idx:
                    sw[i].s = PyIndi.ISS_ON
                else:
                    sw[i].s = PyIndi.ISS_OFF
            self.client.sendNewSwitch(sw)

    def key_release(self, val):
        if not self.telescope:
            return
        if val == 4 or val == 6:
            sw = self.get_switch("TELESCOPE_MOTION_WE")
            sw[0].s = PyIndi.ISS_OFF
            sw[1].s = PyIndi.ISS_OFF
            self.client.sendNewSwitch(sw)
        if val == 2 or val == 8:
            sw = self.get_switch("TELESCOPE_MOTION_NS")
            sw[0].s = PyIndi.ISS_OFF
            sw[1].s = PyIndi.ISS_OFF
            self.client.sendNewSwitch(sw)

    def get_switch(self, name):
        if not self.telescope:
            return None
        sw = self.telescope_obj.getSwitch(name)
        return sw

    def do_connect(self):
        if self.busy:
            return
        self.busy = time.time()
        self.errored = None
        self.telescope = None
        self.client.setServer(
            self.parent.param["indi/hostname"],
            self.parent.param["indi/port"])
        if not self.client.connectServer():
            self.errored = "Error connecting"
            self.busy = None

    def periodic(self):
        if self.busy and time.time() < self.busy + 1:
            return True
        self.busy = None
        if self.controls_dialog:
            self.controls_dialog.update_ui()
        return True
