#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_gui.py – GUI-Setup-Assistent für die DHL-Etikettensoftware (GTK3).

Läuft auf Linux Mint/Ubuntu sofort (PyGObject/GTK3 ist dort vorinstalliert).
Ablauf:
  1) Formular: Drucker, Mediengröße, Etikettengröße, Watch-Modus, Marke-Position
  2) "Installation starten" → install.sh (nicht-interaktiv) läuft im Hintergrund,
     Ausgabe wird live ins Fenster gestreamt
  3) Erfolgsmeldung + optionaler GUI-Kalibrierdialog (jeder Testdruck nur nach
     Bestätigung), danach Fenster schließen – im Hintergrund läuft der Watcher.
"""

import os
import sys
import threading
from pathlib import Path

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib
except (ImportError, ValueError) as exc:  # Fallback ohne GTK
    print(f"GTK/PyGObject nicht verfügbar: {exc}\n"
          "Diese GUI braucht python3-gi (auf Linux Mint/Ubuntu vorinstalliert).\n"
          "Alternativ im Terminal installieren:\n  bash install.sh")
    os.system('zenity --error --title="DHL-Setup" '
              '--text="GTK fehlt – bitte im Terminal ausführen: bash install.sh" 2>/dev/null')
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gui_helpers as gh  # noqa: E402

APP_DIR = Path("~/.local/share/dhl-label").expanduser()
CONFIG_FILE = Path("~/.config/dhl-label/config.conf").expanduser()
HERE = Path(__file__).resolve().parent
INSTALL_SH = HERE / "install.sh"
HOME = Path.home()


def ui(func, *args):
    """Führt func im GTK-Hauptthread aus (aus Worker-Threads aufrufen)."""
    GLib.idle_add(func, *args)


class SetupWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="DHL-Etikettensoftware – Setup")
        self.set_default_size(720, 680)
        self.set_border_width(12)
        self.set_position(Gtk.WindowPosition.CENTER)

        self.installing = False

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(outer)

        title = Gtk.Label(xalign=0)
        title.set_markup("<b><big>DHL-Etikettensoftware – Setup</big></b>\n"
                         "Druckt die DHL-Versandmarke automatisch auf den Etikettendrucker "
                         "(USB oder WLAN).\nNach der Installation läuft das Programm im "
                         "Hintergrund – es startet bei jeder Anmeldung selbst.")
        outer.pack_start(title, False, False, 0)

        form = Gtk.Grid(column_spacing=10, row_spacing=8)
        outer.pack_start(form, False, False, 4)
        row = 0

        def add_label(text, r):
            lbl = Gtk.Label(xalign=0)
            lbl.set_markup(text)
            lbl.set_hexpand(False)
            form.attach(lbl, 0, r, 1, 1)
            return lbl

        # --- Drucker ---
        add_label("<b>Drucker</b> (USB oder WLAN):", row)
        self.printer_combo = Gtk.ComboBoxText()
        self.printer_combo.set_hexpand(True)
        form.attach(self.printer_combo, 1, row, 1, 1)
        self.printer_combo.connect("changed", self.on_printer_changed)
        refresh_btn = Gtk.Button(label="Neu laden")
        refresh_btn.connect("clicked", lambda b: self.load_printers())
        form.attach(refresh_btn, 2, row, 1, 1)
        row += 1

        self.printer_hint = Gtk.Label(xalign=0)
        self.printer_hint.set_markup("<small>Kein Drucker? Gerät verbinden, dann „Neu laden“. "
                                     "Linux Mint richtet Drucker automatisch ein.</small>")
        form.attach(self.printer_hint, 1, row, 2, 1)
        row += 1

        # --- Mediengröße ---
        add_label("<b>Mediengröße</b> (CUPS-Name der Etikettengröße):", row)
        self.media_combo = Gtk.ComboBoxText()
        form.attach(self.media_combo, 1, row, 1, 1)
        row += 1
        self.media_hint = Gtk.Label(xalign=0)
        self.media_hint.set_markup("<small>Z.B. „4x6“. Vorausgewählt ist, was der Drucker meldet "
                                   "– in der Regel einfach übernehmen.</small>")
        form.attach(self.media_hint, 1, row, 2, 1)
        row += 1

        # --- Etikettengröße ---
        add_label("<b>Etikettengröße der Rolle</b> (mm, Breite x Höhe):", row)
        self.target_entry = Gtk.Entry()
        self.target_entry.set_text("100x150")
        self.target_entry.set_hexpand(True)
        form.attach(self.target_entry, 1, row, 1, 1)
        row += 1
        self.target_hint = Gtk.Label(xalign=0)
        self.target_hint.set_markup("<small>Der Vretti nutzt meist 100x150-mm-Rollen (synonym zu 4\"x6\"). "
                                    "Die Marke wird automatisch gedreht und exakt auf das Etikett eingepasst, "
                                    "damit Barcode/QR-Code unverzerrt und scannbar bleiben.</small>")
        self.target_hint.set_line_wrap(True)
        form.attach(self.target_hint, 1, row, 2, 1)
        row += 1

        # --- Watch-Modus ---
        add_label("<b>Wann soll gedruckt werden?</b>", row)
        self.mode_downloads = Gtk.RadioButton.new_with_label(
            None, "PDFs im Downloads-Ordner automatisch drucken (mit Namensfilter)")
        form.attach(self.mode_downloads, 1, row, 2, 1)
        row += 1
        self.pattern_entry = Gtk.Entry()
        self.pattern_entry.set_text("versand|dhl|paket")
        form.attach(self.pattern_entry, 1, row, 1, 1)
        pattern_hint = Gtk.Label(xalign=0)
        pattern_hint.set_markup("<small>Druckt nur PDFs, deren Name das enthält "
                                "(Mehrfach mit | trennen, Groß-/Kleinschreibung egal).</small>")
        form.attach(pattern_hint, 2, row, 1, 1)
        row += 1

        self.mode_custom = Gtk.RadioButton.new_with_label_from_widget(
            self.mode_downloads, "Eigener Ordner überwachen (alle PDFs dort werden gedruckt)")
        form.attach(self.mode_custom, 1, row, 2, 1)
        row += 1

        self.folder_btn = Gtk.FileChooserButton(title="Watch-Ordner wählen",
                                                action=Gtk.FileChooserAction.SELECT_FOLDER)
        self.folder_btn.set_current_folder(str(HOME / "Downloads"))
        form.attach(self.folder_btn, 1, row, 1, 1)
        self.mode_downloads.connect("toggled", self.on_mode_changed)
        self.mode_custom.connect("toggled", self.on_mode_changed)
        row += 1

        # --- Marke-Position ---
        add_label("<b>Wo sitzt die Marke im A4-PDF?</b>", row)
        self.side_top = Gtk.RadioButton.new_with_label(None, "Obere Hälfte")
        form.attach(self.side_top, 1, row, 1, 1)
        self.side_bottom = Gtk.RadioButton.new_with_label_from_widget(self.side_top, "Untere Hälfte")
        form.attach(self.side_bottom, 2, row, 1, 1)
        row += 1

        # --- Install-Button ---
        self.install_btn = Gtk.Button(label="Installation starten")
        self.install_btn.get_style_context().add_class("suggested-action")
        self.install_btn.set_hexpand(True)
        self.install_btn.connect("clicked", self.on_install_clicked)
        outer.pack_start(self.install_btn, False, False, 6)

        # --- Status/Log ---
        self.status_label = Gtk.Label(xalign=0)
        self.status_label.set_line_wrap(True)
        outer.pack_start(self.status_label, False, False, 2)

        log_frame = Gtk.Frame(label="Installations-Verlauf")
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_min_content_height(180)
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll.add(self.log_view)
        log_frame.add(scroll)
        outer.pack_start(log_frame, True, True, 4)

        self.load_printers()

    # ------------------------------------------------------------- Helpers

    def log(self, text):
        buf = self.log_view.get_buffer()
        buf.insert(buf.get_end_iter(), text.rstrip("\n") + "\n")
        self.log_view.scroll_mark_onscreen(buf.get_insert())

    def selected_printer(self):
        idx = self.printer_combo.get_active()
        if idx < 0:
            return None
        text = self.printer_combo.get_active_text()  # "name — status"
        if not text or text.startswith("("):  # "(kein Drucker gefunden)"
            return None
        return text.split(" — ")[0].strip()

    def selected_media(self):
        text = self.media_combo.get_active_text()
        return text if text else None

    # ------------------------------------------------------------- Handlers

    def load_printers(self):
        self.printer_combo.remove_all()
        self.media_combo.remove_all()
        printers = gh.list_printers()
        if not printers:
            self.printer_combo.append_text("(kein Drucker gefunden)")
            self.printer_combo.set_active(0)
            self.printer_hint.set_markup(
                '<span foreground="red">Kein Drucker in CUPS gefunden. Vretti verbinden '
                "(USB oder WLAN) und „Neu laden“ klicken. Mint richtet Drucker automatisch ein.</span>")
            return
        for name, status in printers:
            self.printer_combo.append_text(f"{name} — {status}")
        self.printer_combo.set_active(0)

    def on_printer_changed(self, combo):
        self.media_combo.remove_all()
        printer = self.selected_printer()
        if not printer:
            return
        sizes, default, raw = gh.media_sizes(printer)
        if not sizes:
            sizes, default = ["4x6"], "4x6"
            self.media_hint.set_markup(
                "<small>Drucker meldet keine Mediengrößen – Standard „4x6“ vorausgewählt. "
                "Falls der Druck falsche Maße hat, Name in ~/.config/dhl-label/config.conf anpassen.</small>")
        idx_default = 0
        for i, s in enumerate(sizes):
            self.media_combo.append_text(s)
            if s == default:
                idx_default = i
        self.media_combo.set_active(idx_default)

    def on_mode_changed(self, radio):
        downloads = self.mode_downloads.get_active()
        self.pattern_entry.set_sensitive(downloads)
        self.folder_btn.set_sensitive(not downloads)

    def validate(self):
        printer = self.selected_printer()
        if not printer:
            return "Bitte zuerst einen Drucker auswählen (oder „Neu laden“)."
        media = self.selected_media()
        if not media:
            return "Bitte eine Mediengröße auswählen."
        try:
            target_text = self.target_entry.get_text().strip()
            gh.parse_size_mm(target_text)
        except ValueError as exc:
            return str(exc)
        if self.mode_downloads.get_active():
            pattern = self.pattern_entry.get_text().strip()
            if not pattern:
                return "Namensfilter darf nicht leer sein (sonst würde JEDE PDF gedruckt)."
        return None

    def on_install_clicked(self, btn):
        if self.installing:
            return
        error = self.validate()
        if error:
            self.show_error(error)
            return
        self.installing = True
        self.install_btn.set_sensitive(False)
        self.status_label.set_markup("<b>Installation läuft…</b> (Passwortdialog kann erscheinen)")

        printer = self.selected_printer()
        media = self.selected_media()
        target = self.target_entry.get_text().strip()
        downloads = self.mode_downloads.get_active()
        watch_mode = "downloads" if downloads else "custom"
        watch_dir = self.folder_btn.get_filename() or str(HOME / "Downloads")
        pattern = self.pattern_entry.get_text().strip() if downloads else ""
        side = "top" if self.side_top.get_active() else "bottom"

        cmd = gh.build_install_cmd(
            INSTALL_SH, printer=printer, media=media, target=target,
            watch_mode=watch_mode, watch_dir=watch_dir, pattern=pattern, side=side)

        self.log(f"$ {' '.join(cmd)}\n")

        def worker():
            import subprocess
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True,
                                        bufsize=1, errors="replace")
                for line in proc.stdout:
                    ui(self.log, line)
                proc.wait()
                ui(self.on_install_done, proc.returncode)
            except Exception as exc:
                ui(self.log, f"\nFehler: {exc}\n")
                ui(self.on_install_done, 1)

        threading.Thread(target=worker, daemon=True).start()

    def on_install_done(self, rc):
        self.installing = False
        if rc == 0:
            self.status_label.set_markup(
                '<span foreground="green"><b>Fertig! Das Programm läuft jetzt im Hintergrund.</b></span>\n'
                "Ab sofort: DHL-PDF herunterladen → die Marke druckt automatisch.\n"
                "Der Hintergrunddienst startet bei jeder Anmeldung selbst – "
                "du musst nichts ein- oder ausschalten.")
            self.show_calibration_button()
        else:
            self.status_label.set_markup(
                '<span foreground="red"><b>Installation fehlgeschlagen.</b></span> '
                "Details im Verlauf oben. Den Knoten siehst du am Ende der Ausgabe.")
            self.install_btn.set_sensitive(True)

    def show_calibration_button(self):
        if getattr(self, "calibrate_btn", None):
            return
        self.calibrate_btn = Gtk.Button(label="Jetzt kalibrieren (Testdrucke)")
        self.calibrate_btn.get_style_context().add_class("suggested-action")
        self.calibrate_btn.connect("clicked", lambda b: CalibrationWindow(self).show_all())
        outer = self.get_child()  # Box
        outer.pack_start(self.calibrate_btn, False, False, 4)
        close_btn = Gtk.Button(label="Fertig – Fenster schließen")
        close_btn.connect("clicked", lambda b: self.destroy())
        outer.pack_start(close_btn, False, False, 2)
        self.show_all()

    def show_error(self, text):
        dlg = Gtk.MessageDialog(transient_for=self, flags=0,
                                message_type=Gtk.MessageType.ERROR,
                                buttons=Gtk.ButtonsType.OK, text=text)
        dlg.run()
        dlg.destroy()


class CalibrationWindow(Gtk.Window):
    """GUI-Kalibrierung: Variante wählen → Testdruck nur nach Bestätigung."""

    VARIANTS = gh.calibration_variants()

    def __init__(self, parent):
        super().__init__(title="DHL-Kalibrierung")
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(680, 520)
        self.set_border_width(12)
        self.busy = False

        cfg = gh.read_installed_config(CONFIG_FILE)
        self.printer = cfg["printer"]
        self.media = cfg["media"]
        self.extra_options = cfg["extra_options"]
        self.venv_python = APP_DIR / "venv" / "bin" / "python"
        self.dhl_label_py = APP_DIR / "dhl_label.py"

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(box)

        intro = Gtk.Label(xalign=0)
        intro.set_markup(
            "<b>Kalibrierung</b>\n"
            "Wähle eine Variante, bestätige den Testdruck und vergleiche die Ausdrucke:\n"
            "Passt die Marke komplett auf das Etikett und ist der Barcode scannbar?\n"
            f"Drucker: <b>{self.printer}</b> · Medium: <b>{self.media}</b>\n"
            "Beste Variante später in ~/.config/dhl-label/config.conf eintragen "
            "(oder dieses Setup erneut laufen lassen).")
        intro.set_line_wrap(True)
        box.pack_start(intro, False, False, 0)

        file_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        file_box.pack_start(Gtk.Label(label="DHL-PDF:"), False, False, 0)
        self.pdf_btn = Gtk.FileChooserButton(title="DHL-PDF auswählen",
                                             action=Gtk.FileChooserAction.OPEN)
        pdf_filter = Gtk.FileFilter()
        pdf_filter.set_name("PDF-Dateien")
        pdf_filter.add_pattern("*.pdf")
        self.pdf_btn.add_filter(pdf_filter)
        try:
            self.pdf_btn.set_current_folder(cfg["watch_dir"])
        except Exception:
            self.pdf_btn.set_current_folder(str(HOME / "Downloads"))
        file_box.pack_start(self.pdf_btn, True, True, 0)
        box.pack_start(file_box, False, False, 0)

        variant_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        variant_box.pack_start(Gtk.Label(label="Variante:"), False, False, 0)
        self.variant_combo = Gtk.ComboBoxText()
        for name, _args in self.VARIANTS:
            self.variant_combo.append_text(name)
        self.variant_combo.set_active(0)
        self.variant_combo.set_hexpand(True)
        variant_box.pack_start(self.variant_combo, True, True, 0)
        self.print_btn = Gtk.Button(label="Testdruck starten…")
        self.print_btn.get_style_context().add_class("suggested-action")
        self.print_btn.connect("clicked", self.on_print_clicked)
        variant_box.pack_start(self.print_btn, False, False, 0)
        box.pack_start(variant_box, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_min_content_height(200)
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll.add(self.log_view)
        frame = Gtk.Frame(label="Ausgabe")
        frame.add(scroll)
        box.pack_start(frame, True, True, 4)

        close_btn = Gtk.Button(label="Fenster schließen")
        close_btn.connect("clicked", lambda b: self.destroy())
        box.pack_start(close_btn, False, False, 2)

    def log(self, text):
        buf = self.log_view.get_buffer()
        buf.insert(buf.get_end_iter(), text.rstrip("\n") + "\n")
        self.log_view.scroll_mark_onscreen(buf.get_insert())

    def on_print_clicked(self, btn):
        if self.busy:
            return
        src = self.pdf_btn.get_filename()
        if not src:
            self.message(Gtk.MessageType.ERROR, "Bitte zuerst die DHL-PDF auswählen.")
            return
        idx = self.variant_combo.get_active()
        name, variant_args = self.VARIANTS[idx]

        dlg = Gtk.MessageDialog(transient_for=self, flags=0,
                                message_type=Gtk.MessageType.QUESTION,
                                buttons=Gtk.ButtonsType.YES_NO,
                                text=f"TESTDRUCK jetzt ausführen?\n\n{name}")
        dlg.set_secondary_text("Es wird ein Etikett auf dem Vretti gedruckt. "
                               "Beschrifte es nach dem Ausdruck.")
        answer = dlg.run()
        dlg.destroy()
        if answer != Gtk.ResponseType.YES:
            return

        self.busy = True
        self.print_btn.set_sensitive(False)
        out = Path(os.path.expanduser("~/.cache/dhl-label-calibration")) / f"variante{idx+1}.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)

        def worker():
            import subprocess
            crop_cmd = gh.build_crop_cmd(self.venv_python, self.dhl_label_py, src, out, variant_args)
            ui(self.log, f"$ {' '.join(str(c) for c in crop_cmd)}")
            rc, outp = gh.run_cmd(crop_cmd, timeout=60)
            ui(self.log, outp or "(keine Ausgabe)")
            if rc != 0:
                ui(self.log, f"FEHLER beim Aufbereiten (rc={rc}).\n")
                ui(self.done)
                return
            print_cmd = gh.build_print_cmd(self.printer, self.media, out, self.extra_options)
            ui(self.log, f"$ {' '.join(print_cmd)}")
            rc2, outp2 = gh.run_cmd(print_cmd, timeout=30)
            ui(self.log, outp2 or "(keine Ausgabe)")
            if rc2 == 0:
                ui(self.log, "Druckauftrag gesendet. Etikette beschriften!\n")
            else:
                ui(self.log, f"FEHLER beim Drucken (rc={rc2}). Drucker erreichbar?\n")
            ui(self.done)

        threading.Thread(target=worker, daemon=True).start()

    def done(self):
        self.busy = False
        self.print_btn.set_sensitive(True)

    def message(self, mtype, text):
        dlg = Gtk.MessageDialog(transient_for=self, flags=0, message_type=mtype,
                                buttons=Gtk.ButtonsType.OK, text=text)
        dlg.run()
        dlg.destroy()


def main():
    ok, problems = gh.check_environment()
    if not ok:
        try:
            dlg = Gtk.MessageDialog(transient_for=None, flags=0,
                                    message_type=Gtk.MessageType.ERROR,
                                    buttons=Gtk.ButtonsType.CLOSE,
                                    text="Voraussetzungen fehlen")
            dlg.format_secondary_text("\n".join(problems))
            dlg.run()
            dlg.destroy()
        except Exception:
            print("\n".join(problems))
        sys.exit(1)
    win = SetupWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
