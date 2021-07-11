
import pathlib
import os
import gi
from fih_cam import list_zwo_cams
from fih_indi import Indi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk


def get_dialog(parent, message, title, default):
    dialogWindow = Gtk.MessageDialog(
        parent=parent,
        modal=True,
        destroy_with_parent=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.OK_CANCEL,
        text=message)
    dialogWindow.set_title(title)
    dialogBox = dialogWindow.get_content_area()
    userEntry = Gtk.Entry()
    userEntry.set_text(default)
    userEntry.set_size_request(250, 0)
    userEntry.connect(
        "activate", lambda w: dialogWindow.response(Gtk.ResponseType.OK))
    dialogBox.pack_end(userEntry, False, False, 0)
    dialogWindow.show_all()
    response = dialogWindow.run()
    text = userEntry.get_text()
    dialogWindow.destroy()
    if (response == Gtk.ResponseType.OK) and (text != ''):
        return text
    else:
        return None


class ImagerCmd(Gtk.MenuBar):

    IMG_FIRST = 0
    IMG_LAST = -1
    IMG_NEXT = -2
    IMG_PREV = -3
    IMG_REDRAW = -4

    KEY_MAP = {
        Gdk.KEY_KP_1: 1,
        Gdk.KEY_KP_End: 1,
        Gdk.KEY_Down: 2,
        Gdk.KEY_KP_Down: 2,
        Gdk.KEY_KP_2: 2,
        Gdk.KEY_KP_Page_Down: 3,
        Gdk.KEY_KP_3: 3,
        Gdk.KEY_KP_Left: 4,
        Gdk.KEY_KP_4: 4,
        Gdk.KEY_Left: 4,
        Gdk.KEY_Right: 6,
        Gdk.KEY_KP_Right: 6,
        Gdk.KEY_KP_6: 6,
        Gdk.KEY_KP_Home: 7,
        Gdk.KEY_KP_7: 7,
        Gdk.KEY_Up: 8,
        Gdk.KEY_KP_Up: 8,
        Gdk.KEY_KP_8: 8,
        Gdk.KEY_KP_Page_Up: 9,
        Gdk.KEY_KP_9: 9,
    }

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
        return item

    def add_check(self, menu, name, command, on=False):
        item = Gtk.CheckMenuItem(label=name)
        if on:
            item.set_active(True)
        item.connect("activate", command)
        menu.append(item)
        return item

    def add_radio(self, menu, group, name, command, active):
        item = Gtk.RadioMenuItem(
            label=name, group=self._groups.get(group, None))
        self._groups[group] = item
        item.connect("activate", command)
        if active:
            item.set_active(active)
        menu.append(item)
        return item

    def add_separator(self, menu):
        menu.append(Gtk.SeparatorMenuItem())

    def __init__(self, parent):
        self.p = parent
        self.w = {}
        Gtk.MenuBar.__init__(self)
        self._groups = {}

        file_menu = self.add_sub_menu("_File")
        self.add_entry(
            file_menu, "Open Picture", self.open_picture)
        self.add_entry(
            file_menu, "Open Directory", self.open_directory)
        self.add_entry(
            file_menu, "Open ZWO/ASI Cam", self.open_zwo)
        self.add_separator(file_menu)
        self.add_entry(
            file_menu, "Load Configuration", self.load_conf)
        self.add_entry(
            file_menu, "Save Configuration", self.save_conf)
        self.add_separator(file_menu)
        self.add_entry(file_menu, "INDI Menu", self.show_indi)
        self.add_separator(file_menu)
        self.add_entry(
            file_menu, "Exit", self.exit_app)

        view_menu = self.add_sub_menu("_View")
        self.w["force_gray"] = self.add_check(
            view_menu, "Force Gray", self.force_gray)
        self.w["gamma_stretch"] = self.add_check(
            view_menu, "Gamma Stretch", self.gamma_stretch)
        self.w["scale"] = self.add_check(
            view_menu, "Zoom to fit", self.scale, True)
        self.w["invert"] = self.add_check(
            view_menu, "Invert", self.invert, False)
        self.add_separator(view_menu)
        for n in (0, 1, 10, 50, 100):
            self.w[f"histogram_stretch_percent_{n}"] = self.add_radio(
                view_menu, 'histogram_stretch',
                "Histogram stretch %.1f %%" % (n / 10),
                lambda w, n=n: self.histo_stretch(w, n), n == 0)

        cam_menu = self.add_sub_menu("_Cam")
        self.add_entry(
            cam_menu, "Controls", self.cam_controls)
        self.w["cam_run"] = self.add_check(
            cam_menu, "Run", self.cam_run)
        self.add_separator(cam_menu)
        self.w["indi/keys"] = self.add_check(
            cam_menu, "Enable Indi Keys", self.indi_keys,
            self.p.param["indi/keys"])

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
        self.w["sort_timestamp"] = self.add_check(
            nav_menu, "Sort by date", self.sort_by_date, False)
        self.add_check(
            nav_menu, "Auto reload new pictures", self.auto_reload, False)

        focuser_menu = self.add_sub_menu("F_ocuser")
        self.w["finder_dao"] = self.add_radio(
            focuser_menu, 'star_finder', "Use DAOStarFinder",
            self.sf_dao, True)
        self.w["finder_iraf"] = self.add_radio(
            focuser_menu, 'star_finder', "Use IRAFStarFinder",
            self.sf_iraf, False)
        self.add_separator(focuser_menu)
        self.w["show_nothing"] = self.add_radio(
            focuser_menu, 'focuser_show', "Show Nothing",
            lambda w: self.sf_show(w, "nothing"), True)
        self.w["show_sharpness"] = self.add_radio(
            focuser_menu, 'focuser_show', "Show Sharpness",
            lambda w: self.sf_show(w, "sharpness"), False)
        self.w["show_roundness1"] = self.add_radio(
            focuser_menu, 'focuser_show', "Show Roundness 1",
            lambda w: self.sf_show(w, "roundness1"), False)
        self.w["show_roundness2"] = self.add_radio(
            focuser_menu, 'focuser_show', "Show Roundness 2",
            lambda w: self.sf_show(w, "roundness2"), False)
        self.w["show_hfr"] = self.add_radio(
            focuser_menu, 'focuser_show', "Show HFR",
            lambda w: self.sf_show(w, "hfr"), False)
        self.add_separator(focuser_menu)
        for n in (10, 50, 100, 500, 1000, 5000, 10000):
            self.w[f"n_stars_{n}"] = self.add_radio(
                focuser_menu, 'n_stars', "Show %d stars" % n,
                lambda w, n=n: self.sf_n_stars(w, n), n == 100)
        self.add_separator(focuser_menu)
        self.w["text"] = self.add_check(
            focuser_menu, "Show Value", self.show_text)
        self.add_entry(
            focuser_menu, "Set FWHM", self.set_fwhm)
        self.add_entry(
            focuser_menu, "Set Threshold", self.set_threshold)

        help_menu = self.add_sub_menu("_Help")
        self.add_entry(
            help_menu, "Keyboard shortcut", self.help_keys)

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

    def histo_stretch(self, w, n):
        if w.get_active():
            self.p.set_param("display/histogram_stretch_percent", n)

    def scale(self, w):
        self.p.set_param("display/scale", w.get_active())

    def first_img(self, w):
        self.p.show_img(self.IMG_FIRST)

    def last_img(self, w):
        self.p.show_img(self.IMG_LAST)

    def next_img(self, w):
        self.p.show_img(self.IMG_NEXT)

    def prev_img(self, w):
        self.p.show_img(self.IMG_PREV)

    def multi_reload(self, w):
        self.p.multi_reload()

    def sort_by_date(self, w):
        self.p.set_param("multi/sort_timestamp", w.get_active())
        self.p.multi_reload()

    def auto_reload(self, w):
        self.p.auto_reload(w.get_active())

    def sf_dao(self, w):
        if w.get_active():
            self.p.set_param("focuser/finder", "dao")

    def sf_iraf(self, w):
        if w.get_active():
            self.p.set_param("focuser/finder", "iraf")

    def sf_show(self, w, n):
        if w.get_active():
            self.p.set_param("focuser/show", n)

    def sf_n_stars(self, w, n):
        if w.get_active():
            self.p.set_param("focuser/n_stars", n)

    def show_text(self, w):
        self.p.set_param("focuser/text", w.get_active())

    def set_fwhm(self, w):
        ret = get_dialog(self.p, "Enter FWHM for star finders", "FWHM",
                         "%.2f" % self.p.get_param("focuser/fwhm"))
        try:
            val = float(ret)
        except (TypeError, ValueError):
            return
        self.p.set_param("focuser/fwhm", val)

    def set_threshold(self, w):
        ret = get_dialog(self.p, "Enter threshold (in stds) for star finder",
                         "Threshold",
                         "%.2f" % self.p.get_param("focuser/threshold"))
        try:
            val = float(ret)
        except (TypeError, ValueError):
            return
        self.p.set_param("focuser/threshold", val)

    def save_conf(self, w):
        dest = os.path.join(pathlib.Path.home(), ".config", "fit-image-helper")
        pathlib.Path(dest).mkdir(parents=True, exist_ok=True)
        dialog = Gtk.FileChooserDialog(
            title="Please choose where to save the configuration",
            parent=self.p, action=Gtk.FileChooserAction.SAVE
        )
        dialog.set_filename(os.path.join(dest, "default.fih"))
        dialog.set_current_name("default.fih")
        dialog.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE,
            Gtk.ResponseType.OK,
        )
        filter_fit = Gtk.FileFilter()
        filter_fit.set_name("Configuration files")
        filter_fit.add_pattern("*.fih")
        dialog.add_filter(filter_fit)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            if not filename.endswith('.fih'):
                filename += '.fih'
            self.p.save_conf(filename)
        dialog.destroy()

    def load_conf(self, w):
        dest = os.path.join(pathlib.Path.home(), ".config", "fit-image-helper")
        dialog = Gtk.FileChooserDialog(
            title="Please choose a configuration to load",
            parent=self.p, action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,
            Gtk.ResponseType.OK,
        )
        dialog.set_filename(os.path.join(dest, "dummy"))
        filter_fit = Gtk.FileFilter()
        filter_fit.set_name("Fit images")
        filter_fit.add_pattern("*.fih")
        dialog.add_filter(filter_fit)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.p.load_conf(dialog.get_filename())
        dialog.destroy()

    def update_ui(self, param):
        for i in ("force_gray", "invert", "gamma_stretch", "scale"):
            self.w[i].set_active(param[f"display/{i}"])
        for i in ("indi/keys"):
            self.w[i].set_active(param[i])
        self.w[
            "histogram_stretch_percent_"
            f"{param['display/histogram_stretch_percent']}"].set_active(True)
        self.w["sort_timestamp"].set_active(param["multi/sort_timestamp"])
        self.w["finder_" f"{param['focuser/finder']}"].set_active(True)
        self.w["show_" f"{param['focuser/show']}"].set_active(True)
        self.w["n_stars_" f"{param['focuser/n_stars']}"].set_active(True)
        self.w["text"].set_active(param["focuser/text"])
        self.w["cam_run"].set_active(param["cam/run"])

    def open_zwo(self, w):
        ident = list_zwo_cams(self.p)
        if ident is None:
            return
        self.p.open_cam("zwo", ident)

    def cam_controls(self, w):
        if self.p.cam:
            self.p.cam.controls()

    def cam_run(self, w):
        if not self.p.cam:
            return
        if w.get_active():
            self.p.param["cam/run"] = True
            self.p.cam.start()
        else:
            self.p.param["cam/run"] = False
            self.p.cam.stop()

    def show_indi(self, w):
        if not self.p.indi:
            self.p.indi = Indi(self.p)
        self.p.indi.show_dialog()

    def hook_keys(self):
        self.p.connect("key_press_event", self.handle_key_press)
        self.p.connect("key_release_event", self.handle_key_release)

    def handle_key_press(self, w, ev):
        if ev.state & Gdk.ModifierType.SHIFT_MASK:
            if ev.keyval == Gdk.KEY_Home:
                self.first_img(None)
                return True
            if ev.keyval == Gdk.KEY_End:
                self.last_img(None)
                return True
            if ev.keyval == Gdk.KEY_Page_Up:
                self.prev_img(None)
                return True
            if ev.keyval == Gdk.KEY_Page_Down:
                self.next_img(None)
                return True
        if self.p.indi and self.p.param["indi/keys"]:
            try:
                val = self.KEY_MAP[ev.keyval]
            except KeyError:
                return False
            self.p.indi.key_press(val)
            return True

    def handle_key_release(self, w, ev):
        if self.p.indi and self.p.param["indi/keys"]:
            try:
                val = self.KEY_MAP[ev.keyval]
            except KeyError:
                return False
            self.p.indi.key_release(val)
            return True

    def indi_keys(self, w):
        self.p.set_param("indi/keys", w.get_active())

    def help_keys(self, w):
        dialog = Gtk.MessageDialog(
            transient_for=self.p,
            flags=0,
            title="Keys",
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=(
                "Keys:\n\n"
                "Shift+PgUp   Prev Image\n"
                "Shift+PgDown Next Image\n"
                "Shift+Home   First Image\n"
                "Shift+End    Last Image\n"
                "KP_1         Slow Slew\n"
                "KP_3         Medium Slew\n"
                "KP_5         Fast Slew\n"
                "KP_9         Fastest Slew\n"
                "KP_8, Up     Fastest N\n"
                "KP_2, Down   Fastest S\n"
                "KP_4, Left   Slew W\n"
                "KP_6, Right  Slew E\n"
            )
        )
        dialog.run()
        dialog.destroy()
