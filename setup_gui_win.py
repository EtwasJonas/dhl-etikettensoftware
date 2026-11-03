#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_gui_win.py – Setup-Assistent für Windows 11 (tkinter).

GTK3/PyGObject ist unter Windows nicht praktikabel; tkinter ist in der
Windows-Python-Installation enthalten und wird von PyInstaller gebündelt.

Ablauf:
  1) Formular: Drucker, Papierformat (Windows-Treiber), Etikettengröße,
     Zuschnitt, Watch-Modus (Downloads mit Namensfilter oder eigener Ordner),
     Position der Marke im A4-PDF, Autostart
  2) „Einrichten“ → schreibt %APPDATA%/dhl-label/config.conf, richtet die
     Autostart-Verknüpfung im Startmenü-Autostart-Ordner ein (kein Admin
     nötig) und startet einen laufenden Watcher mit den neuen Werten neu
  3) Kalibrieren: Testdrucke (Variante 1/2/3/5/6) – jeder Druck passiert
     nur nach Bestätigung; Variante 4 (Ghostscript) gibt es nur unter Linux

Start: `dhl-label setup` bzw. Doppelklick auf die EXE (ohne Argument öffnet
die EXE dieses Fenster). Erneut einrichten zeigt „✓ Bereits installiert“
mit Vorbefüllung, Deinstallieren entfernt Autostart + Einstellungen.
"""

import os
import sys
import threading
import tempfile
from pathlib import Path
from types import SimpleNamespace

import dhl_label
import gui_helpers as gh
import win_backend

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

DEFAULT_PATTERN = "versand|dhl|paket"

# Kalibriervarianten (ohne Variante 4 – Ghostscript nur unter Linux)
CALIBRATION_VARIANTS = [
    ("1: obere Hälfte exakt", {}),
    ("2: 5 mm oben abgeschnitten", {"trim_top_mm": 5.0}),
    ("3: 5 mm unten abgeschnitten", {"trim_bottom_mm": 5.0}),
    ("5: gedreht + exakt auf 100x150 mm eingepasst",
     {"target_mm": "100x150", "rotate": "auto"}),
    ("6: gedreht + exakt auf 101,6x152,4 mm (4\"x6\") eingepasst",
     {"target_mm": "101.6x152.4", "rotate": "auto"}),
]


def base_dir():
    """Repo- bzw. entpackte-EXE-Ordner (für icon.ico)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        return Path(meipass) if meipass else Path(sys.executable).parent
    return Path(__file__).resolve().parent


class SetupWindow:
    def __init__(self, root):
        self.root = root
        root.title("DHL-Etikettensoftware – Setup")
        root.minsize(720, 620)
        root.geometry("780x720")

        self.busy = False
        self.printers = []
        self.installed_cfg = None
        self._action_buttons = []

        self._build_ui()
        ok, problems = gh.check_environment()
        if not ok:
            self._log("Voraussetzungen fehlen:")
            for problem in problems:
                self._log("  - " + problem)
        self.refresh_state()
        self.load_printers_async()

    # ------------------------------------------------------------ UI-Aufbau

    def _build_ui(self):
        # Tk-Variablen zuerst (keine Walrus-Zuweisungen auf Attribute möglich)
        self.printer_var = tk.StringVar()
        self.paper_var = tk.StringVar()
        self.target_var = tk.StringVar(value="100x150")
        self.trim_top_var = tk.StringVar(value="0")
        self.trim_bottom_var = tk.StringVar(value="0")
        self.trim_left_var = tk.StringVar(value="0")
        self.trim_right_var = tk.StringVar(value="0")
        self.watch_mode_var = tk.StringVar(value="downloads")
        self.watch_dir_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.pattern_var = tk.StringVar(value=DEFAULT_PATTERN)
        self.side_var = tk.StringVar(value="top")
        self.autostart_var = tk.BooleanVar(value=True)

        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        title = ttk.Label(main, text="DHL-Etikettensoftware – Setup",
                          font=("Segoe UI", 14, "bold"))
        title.pack(anchor="w")
        intro = ttk.Label(main, text=(
            "Druckt die DHL-Versandmarke aus dem A4-PDF automatisch auf den "
            "Etikettendrucker (USB oder WLAN).\nNach dem Einrichten läuft ein "
            "Watcher im Hintergrund – er startet bei jeder Windows-Anmeldung "
            "selbst und druckt, wenn eine neue DHL-PDF im Watch-Ordner landet."),
            wraplength=740, justify="left")
        intro.pack(anchor="w", pady=(2, 8))

        self.banner = ttk.Label(main, text="", font=("Segoe UI", 10, "bold"))
        self.banner.pack(anchor="w", pady=(0, 6))

        form = ttk.Frame(main)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        row = 0

        def add_label(text, r, bold=False):
            lbl = ttk.Label(form, text=text,
                            font=("Segoe UI", 9, "bold") if bold else None)
            lbl.grid(row=r, column=0, sticky="nw", padx=(0, 10), pady=3)
            return lbl

        # Drucker
        add_label("Drucker:", row, bold=True)
        self.printer_combo = ttk.Combobox(form, state="readonly",
                                          textvariable=self.printer_var)
        self.printer_combo.grid(row=row, column=1, sticky="ew", pady=3)
        self.printer_combo.bind("<<ComboboxSelected>>", self.on_printer_changed)
        ttk.Button(form, text="Neu laden", command=self.load_printers_async,
                   width=12).grid(row=row, column=2, padx=(8, 0), pady=3)
        row += 1
        ttk.Label(form, text="Kein Drucker in der Liste? Gerät anstecken, "
                             "dann „Neu laden“. USB-Drucker richtet Windows "
                             "automatisch ein.", wraplength=560,
                  foreground="#555").grid(row=row, column=1, columnspan=2,
                                          sticky="w", pady=(0, 4))
        row += 1

        # Papierformat
        add_label("Papierformat\n(Windows-Treiber):", row, bold=True)
        self.paper_combo = ttk.Combobox(form, state="readonly",
                                        textvariable=self.paper_var)
        self.paper_combo.grid(row=row, column=1, sticky="ew", pady=3)
        row += 1
        ttk.Label(form, text="Das Papierformat, das der Drucker-Treiber meldet "
                             "(z.B. „User Defined 100x150mm“) – meist einfach "
                             "übernehmen.", wraplength=560,
                  foreground="#555").grid(row=row, column=1, columnspan=2,
                                          sticky="w", pady=(0, 4))
        row += 1

        # Etikettengröße
        add_label("Etikettengröße (mm):", row, bold=True)
        self.target_entry = ttk.Entry(form, textvariable=self.target_var, width=16)
        self.target_entry.grid(row=row, column=1, sticky="w", pady=3)
        row += 1
        ttk.Label(form, text="Größe der Etikettenrolle, z.B. „100x150“ (Breite "
                             "x Höhe). Leer lassen = nur croppen, ohne Einpassen.",
                  wraplength=560, foreground="#555").grid(row=row, column=1,
                                                          columnspan=2, sticky="w", pady=(0, 4))
        row += 1

        # Zuschnitt
        add_label("Zusätzlich abschneiden:", row, bold=True)
        trim_frame = ttk.Frame(form)
        trim_frame.grid(row=row, column=1, sticky="w", pady=3)
        ttk.Label(trim_frame, text="oben:").pack(side="left")
        self.trim_top_entry = ttk.Entry(trim_frame, width=5,
                                        textvariable=self.trim_top_var)
        self.trim_top_entry.pack(side="left", padx=(4, 10))
        ttk.Label(trim_frame, text="unten:").pack(side="left")
        self.trim_bottom_entry = ttk.Entry(trim_frame, width=5,
                                           textvariable=self.trim_bottom_var)
        self.trim_bottom_entry.pack(side="left", padx=(4, 10))
        ttk.Label(trim_frame, text="links:").pack(side="left")
        self.trim_left_entry = ttk.Entry(trim_frame, width=5,
                                         textvariable=self.trim_left_var)
        self.trim_left_entry.pack(side="left", padx=(4, 10))
        ttk.Label(trim_frame, text="rechts:").pack(side="left")
        self.trim_right_entry = ttk.Entry(trim_frame, width=5,
                                          textvariable=self.trim_right_var)
        self.trim_right_entry.pack(side="left", padx=4)
        row += 1
        ttk.Label(form, text="mm, die zusätzlich weggeschnitten werden (Kalibrierung: "
                             "falls Inhalte angeschnitten werden oder Ränder ungleich "
                             "sind – meist 0 lassen).", wraplength=560,
                  foreground="#555").grid(row=row, column=1, columnspan=2,
                                          sticky="w", pady=(0, 4))
        row += 1

        # Watch-Modus
        add_label("Wann drucken?", row, bold=True)
        mode_frame = ttk.Frame(form)
        mode_frame.grid(row=row, column=1, sticky="w", pady=3)
        ttk.Radiobutton(mode_frame, text="Downloads-Ordner überwachen (nur "
                        "Dateien mit „dhl“/„versand“/„paket“ im Namen)",
                        value="downloads", variable=self.watch_mode_var,
                        command=self._on_mode_changed).pack(anchor="w")
        ttk.Radiobutton(mode_frame, text="Eigenen Ordner überwachen (alle PDFs)",
                        value="custom", variable=self.watch_mode_var,
                        command=self._on_mode_changed).pack(anchor="w")
        row += 1

        # Watch-Ordner
        add_label("Watch-Ordner:", row, bold=True)
        dir_frame = ttk.Frame(form)
        dir_frame.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
        dir_frame.columnconfigure(0, weight=1)
        self.watch_dir_entry = ttk.Entry(dir_frame,
                                         textvariable=self.watch_dir_var)
        self.watch_dir_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(dir_frame, text="Durchsuchen…", command=self._browse_dir,
                   width=14).grid(row=0, column=1, padx=(8, 0))
        row += 1

        # Namensfilter
        add_label("Namensfilter:", row, bold=True)
        self.pattern_entry = ttk.Entry(form,
                                       textvariable=self.pattern_var, width=30)
        self.pattern_entry.grid(row=row, column=1, sticky="w", pady=3)
        row += 1
        ttk.Label(form, text="Wörter (mit | getrennt), die im Dateinamen stehen "
                             "müssen – nur im Downloads-Modus relevant.",
                  wraplength=560, foreground="#555").grid(row=row, column=1,
                                                          columnspan=2, sticky="w", pady=(0, 4))
        row += 1

        # Position der Marke
        add_label("Position der Marke\nim A4-PDF:", row, bold=True)
        side_frame = ttk.Frame(form)
        side_frame.grid(row=row, column=1, sticky="w", pady=3)
        ttk.Radiobutton(side_frame, text="Obere Hälfte (DHL-Privatkundenportal: Standard)",
                        value="top", variable=self.side_var).pack(anchor="w")
        ttk.Radiobutton(side_frame, text="Untere Hälfte", value="bottom",
                        variable=self.side_var).pack(anchor="w")
        row += 1

        # Autostart
        add_label("Autostart:", row, bold=True)
        ttk.Checkbutton(form, variable=self.autostart_var,
                        text="Watcher bei jeder Windows-Anmeldung automatisch "
                             "starten (Verknüpfung im Autostart-Ordner)"
                        ).grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        # Buttons
        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=(10, 4))
        self.save_btn = ttk.Button(buttons, text="Einrichten", command=self.save)
        self.save_btn.pack(side="left")
        self._action_buttons.append(self.save_btn)
        self.calib_btn = ttk.Button(buttons, text="Kalibrieren…", command=self.calibrate)
        self.calib_btn.pack(side="left", padx=(8, 0))
        self._action_buttons.append(self.calib_btn)
        self.start_btn = ttk.Button(buttons, text="Watcher jetzt starten",
                                    command=self.start_watcher_now)
        self.start_btn.pack(side="left", padx=(8, 0))
        self._action_buttons.append(self.start_btn)
        self.uninstall_btn = ttk.Button(buttons, text="Deinstallieren…",
                                        command=self.uninstall)
        # wird in refresh_state eingeblendet, falls installiert
        self._action_buttons.append(self.uninstall_btn)

        # Protokoll
        log_frame = ttk.LabelFrame(main, text="Protokoll", padding=6)
        log_frame.pack(fill="both", expand=True, pady=(8, 0))
        self.log_text = tk.Text(log_frame, height=9, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True)
        self._on_mode_changed()

    # ------------------------------------------------------------ Helfer

    def _ui(self, fn, *args):
        self.root.after(0, lambda: fn(*args))

    def _log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", str(msg).rstrip() + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for btn in self._action_buttons:
            btn.configure(state=state)

    def _browse_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.watch_dir_var.get() or str(Path.home()))
        if chosen:
            self.watch_dir_var.set(chosen)

    def _on_mode_changed(self):
        state = "normal" if self.watch_mode_var.get() == "downloads" else "disabled"
        self.pattern_entry.configure(state=state)

    # ------------------------------------------------------------ Zustand

    def refresh_state(self):
        installed, cfg = gh.installed_state()
        self.installed_cfg = cfg if installed else None
        if installed:
            self.banner.configure(
                text="✓ Bereits installiert – unten sind die aktuellen Werte eingestellt.",
                foreground="#1a7f37")
            self.save_btn.configure(text="Einstellungen aktualisieren")
            self.uninstall_btn.pack(side="right")
            self.printer_var.set(cfg.get("printer", ""))
            self.paper_var.set(cfg.get("media", ""))
            self.target_var.set(cfg.get("target_size_mm") or "100x150")
            self.watch_mode_var.set(
                "downloads" if cfg.get("watch_mode", "downloads") == "downloads"
                else "custom")
            self.watch_dir_var.set(cfg.get("watch_dir")
                                   or str(Path.home() / "Downloads"))
            self.pattern_var.set(cfg.get("filename_pattern") or DEFAULT_PATTERN)
            self.side_var.set(cfg.get("side", "top"))
            for var, key in ((self.trim_top_var, "trim_top_mm"),
                             (self.trim_bottom_var, "trim_bottom_mm"),
                             (self.trim_left_var, "trim_left_mm"),
                             (self.trim_right_var, "trim_right_mm")):
                raw = (cfg.get(key) or "0").replace(",", ".")
                try:
                    value = float(raw)
                except ValueError:
                    value = 0.0
                var.set(f"{value:g}")
        else:
            self.banner.configure(text="Noch nicht eingerichtet.",
                                  foreground="#555")
            self.save_btn.configure(text="Einrichten")
            self.uninstall_btn.pack_forget()
            self.target_var.set(self.target_var.get() or "100x150")
        self._on_mode_changed()
        running, pid = win_backend.watcher_running()
        if running:
            self._log(f"Watcher: läuft (PID {pid}).")
        else:
            self._log("Watcher: läuft nicht.")

    # ------------------------------------------------------------ Drucker

    def load_printers_async(self):
        if self.busy:
            return
        def work():
            try:
                printers = gh.list_printers()
            except Exception as exc:
                self._ui(self._printers_failed, exc)
                return
            self._ui(self._printers_loaded, printers)
        threading.Thread(target=work, daemon=True).start()

    def _printers_failed(self, exc):
        self._log(f"Drucker konnten nicht gelesen werden: {exc}")

    def _printers_loaded(self, printers):
        self.printers = printers
        names = [name for name, _status in printers]
        self.printer_combo.configure(values=names)
        self._log(f"{len(names)} Drucker gefunden: "
                  + (", ".join(names) if names else "keine"))
        if names and not self.printer_var.get():
            self.printer_var.set(names[0])
        if self.printer_var.get():
            self.load_papers_async()

    def on_printer_changed(self, _event=None):
        self.load_papers_async()

    def load_papers_async(self):
        printer = self.printer_var.get().strip()
        if not printer:
            return
        def work():
            try:
                names, default, _raw = gh.media_sizes(printer)
            except Exception as exc:
                self._ui(self._log, f"Papierformate nicht lesbar ({printer}): {exc}")
                return
            self._ui(self._papers_loaded, names, default)
        threading.Thread(target=work, daemon=True).start()

    def _papers_loaded(self, names, default):
        self.paper_combo.configure(values=names)
        if self.paper_var.get() not in names:  # Vorbefüllung/Installiert behalten
            self.paper_var.set(default or (names[0] if names else ""))
        self._log(f"Papierformate: {', '.join(names) if names else '(keine gemeldet)'}"
                  + (f" – Treiber-Standard: {default}" if default else ""))

    # ------------------------------------------------------------ Speichern

    def save(self):
        if self.busy:
            return
        printer = self.printer_var.get().strip()
        if not printer:
            messagebox.showerror("Fehler", "Bitte zuerst einen Drucker wählen.")
            return
        target_text = self.target_var.get().strip()
        if target_text:
            try:
                gh.parse_size_mm(target_text)
            except ValueError as exc:
                messagebox.showerror("Fehler", str(exc))
                return
        try:
            trim_top = float((self.trim_top_var.get() or "0").replace(",", ".") or 0)
            trim_bottom = float((self.trim_bottom_var.get() or "0").replace(",", ".") or 0)
            trim_left = float((self.trim_left_var.get() or "0").replace(",", ".") or 0)
            trim_right = float((self.trim_right_var.get() or "0").replace(",", ".") or 0)
        except ValueError:
            messagebox.showerror("Fehler", "Zuschnitt muss eine Zahl sein (z.B. 5 oder 2,5).")
            return
        watch_dir = self.watch_dir_var.get().strip()
        if not watch_dir:
            messagebox.showerror("Fehler", "Bitte einen Watch-Ordner angeben.")
            return
        mode = self.watch_mode_var.get()
        pattern = self.pattern_var.get().strip()
        if mode == "downloads" and not pattern:
            messagebox.showerror("Fehler",
                                 "Namensfilter darf im Downloads-Modus nicht leer sein.")
            return

        self._set_busy(True)
        self._log("Speichere Einstellungen ...")

        def work():
            try:
                path = gh.write_config_file(
                    gh.default_config_path(),
                    printer=printer,
                    media=self.paper_var.get().strip(),
                    target_size_mm=target_text,
                    watch_mode=mode,
                    watch_dir=watch_dir,
                    filename_pattern=pattern,
                    side=self.side_var.get(),
                    trim_top_mm=trim_top,
                    trim_bottom_mm=trim_bottom,
                    trim_left_mm=trim_left,
                    trim_right_mm=trim_right)
                self._ui(self._log, f"Konfiguration geschrieben: {path}")
                if getattr(sys, "frozen", False):
                    installed_exe = win_backend.install_exe_copy()
                    if installed_exe:
                        self._ui(self._log,
                                 f"Programm installiert: {installed_exe}")
                if self.autostart_var.get():
                    win_backend.create_autostart_shortcut()
                    self._ui(self._log,
                             f"Autostart eingerichtet: {win_backend.autostart_path()}")
                elif win_backend.remove_autostart_shortcut():
                    self._ui(self._log, "Autostart-Verknüpfung entfernt.")
                running, _pid = win_backend.watcher_running()
                if running:
                    win_backend.kill_watcher()
                    win_backend.spawn_watch_detached()
                    self._ui(self._log,
                             "Watcher lief bereits → mit neuen Einstellungen neu gestartet.")
                self._ui(self._log, "Fertig – ab jetzt wird automatisch gedruckt.")
                self._ui(self.refresh_state)
                self._ui(self._ask_calibrate)
            except Exception as exc:
                self._ui(self._log, f"Fehler beim Einrichten: {exc}")
                self._ui(lambda: messagebox.showerror("Fehler", str(exc)))
            finally:
                self._ui(self._set_busy, False)
        threading.Thread(target=work, daemon=True).start()

    def _ask_calibrate(self):
        if messagebox.askyesno(
                "Einrichten abgeschlossen",
                "Die Einstellungen sind gespeichert.\n\n"
                "Jetzt kalibrieren? Es werden ein bis fünf Testdrucke gemacht –\n"
                "jeder Druck passiert nur nach deiner Bestätigung.\n\n"
                "(Später anytime über „Kalibrieren…“ möglich.)"):
            self.calibrate()

    # ------------------------------------------------------------ Watcher

    def start_watcher_now(self):
        if self.busy:
            return
        running, pid = win_backend.watcher_running()
        if running:
            messagebox.showinfo("Watcher", f"Der Watcher läuft bereits (PID {pid}).")
            return
        try:
            win_backend.spawn_watch_detached()
            self._log("Watcher gestartet – läuft im Hintergrund.")
        except Exception as exc:
            self._log(f"Watcher konnte nicht gestartet werden: {exc}")
            messagebox.showerror("Fehler", str(exc))

    # ------------------------------------------------------------ Deinstall

    def uninstall(self):
        if self.busy:
            return
        if not messagebox.askyesno(
                "Deinstallieren",
                "Watcher beenden, Autostart-Verknüpfung und gespeicherte "
                "Einstellungen entfernen?\n\nDeine PDFs im Watch-Ordner bleiben "
                "erhalten.", icon="warning"):
            return
        self._set_busy(True)

        def work():
            try:
                win_backend.kill_watcher()
                self._ui(self._log, "Watcher beendet.")
                removed = win_backend.remove_autostart_shortcut()
                self._ui(self._log,
                         "Autostart-Verknüpfung entfernt." if removed
                         else "Es gab keine Autostart-Verknüpfung.")
                config = gh.default_config_path()
                existed = config.exists()
                try:
                    config.unlink()
                except FileNotFoundError:
                    existed = False
                self._ui(self._log,
                         f"Einstellungen gelöscht: {config}" if existed
                         else "Es gab keine gespeicherten Einstellungen.")
                self._ui(self.refresh_state)
                self._ui(lambda: messagebox.showinfo(
                    "Deinstalliert",
                    "Die DHL-Etikettensoftware wurde entfernt.\nDeine PDFs "
                    "im Watch-Ordner wurden nicht angefasst."))
            except Exception as exc:
                self._ui(self._log, f"Fehler beim Deinstallieren: {exc}")
                self._ui(lambda: messagebox.showerror("Fehler", str(exc)))
            finally:
                self._ui(self._set_busy, False)
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ Kalibrierung

    def calibrate(self):
        if self.busy:
            return
        config_path = gh.default_config_path()
        if not config_path.exists():
            messagebox.showerror("Kalibrieren",
                                 "Bitte zuerst „Einrichten“ – es gibt noch keine "
                                 "gespeicherten Einstellungen.")
            return
        try:
            cfg = dhl_label.Config(config_path)
        except SystemExit as exc:
            messagebox.showerror("Kalibrieren", str(exc))
            return
        probe = SimpleNamespace(watch_mode=self.watch_mode_var.get(),
                                filename_pattern=self.pattern_var.get())
        src = dhl_label.newest_matching(
            self.watch_dir_var.get().strip() or str(Path.home() / "Downloads"), probe)
        if src is None:
            src = filedialog.askopenfilename(
                title="DHL-PDF für die Kalibrierung wählen",
                filetypes=[("PDF-Dateien", "*.pdf"), ("Alle Dateien", "*.*")])
            if not src:
                return
        self._open_calibration_dialog(Path(src), cfg)

    def _open_calibration_dialog(self, src, cfg):
        win = tk.Toplevel(self.root)
        win.title("Kalibrierung – Testdrucke")
        win.transient(self.root)
        win.grab_set()
        win.minsize(680, 480)

        ttk.Label(win, text="Kalibrierung", font=("Segoe UI", 12, "bold")).pack(
            anchor="w", padx=12, pady=(10, 2))
        ttk.Label(win, text=(
            f"Quelle: {src.name}\n\n"
            "Wähle eine Variante und starte einen Testdruck – jeder Druck passiert "
            "nur nach deiner Bestätigung. Beschrifte jede Etikette mit der "
            "Varianten-Nummer und vergleiche:\n"
            "  1/2/3: Bereich exakt bzw. 5 mm zugeschnitten\n"
            "  5/6: gedreht und exakt auf die Etikettengröße eingepasst "
            "(empfohlen für 4x6-Rollen)\n\n"
            "Variante 4 (Ghostscript-Hardcrop) gibt es nur unter Linux.\n"
            "Passt eine Variante? Trage die Werte im Hauptfenster ein "
            "(Zuschnitt mm, Etikettengröße); falls die Marke auf dem Kopf "
            "steht: in der config.conf [crop] rotate = 270 setzen."),
            wraplength=650, justify="left").pack(anchor="w", padx=12)

        box = ttk.Frame(win, padding=12)
        box.pack(fill="x")
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text="Variante:").grid(row=0, column=0, padx=(0, 8))
        variant_combo = ttk.Combobox(box, state="readonly", width=48,
                                     values=[name for name, _ in CALIBRATION_VARIANTS])
        variant_combo.current(0)
        variant_combo.grid(row=0, column=1, sticky="w")

        calib_log = tk.Text(win, height=10, wrap="word", state="disabled")
        calib_log.pack(fill="both", expand=True, padx=12, pady=8)

        def clog(msg):
            try:
                calib_log.configure(state="normal")
                calib_log.insert("end", str(msg).rstrip() + "\n")
                calib_log.see("end")
                calib_log.configure(state="disabled")
            except tk.TclError:
                pass  # Dialog wurde geschlossen

        buttons = ttk.Frame(win, padding=(12, 0, 12, 12))
        buttons.pack(fill="x")

        def test_print():
            desc = variant_combo.get()
            if not desc:
                return
            number = desc.split(":")[0].strip()
            if not messagebox.askyesno(
                    "Testdruck", f"{desc}\n\nJetzt drucken?", parent=win):
                clog(f"Variante {number}: abgebrochen (nicht bestätigt).")
                return
            clog(f"Variante {number}: wird erzeugt und gedruckt ...")
            overrides = dict(CALIBRATION_VARIANTS[
                [name for name, _ in CALIBRATION_VARIANTS].index(desc)][1])
            tmp = Path(tempfile.gettempdir()) / "dhl-label-calibrate"
            tmp.mkdir(exist_ok=True)
            out = tmp / f"variante{number}.pdf"

            def work():
                try:
                    dhl_label.make_cropped(src, out, cfg, **overrides)
                    ok = dhl_label.print_pdf(out, cfg)
                    self._ui(clog, f"Variante {number}: "
                              + ("gedruckt – Etikette beschriften!" if ok
                                 else "Druck fehlgeschlagen (siehe Protokoll unten)."))
                except Exception as exc:
                    self._ui(clog, f"Variante {number}: Fehler – {exc}")
            threading.Thread(target=work, daemon=True).start()

        ttk.Button(buttons, text="Testdruck starten", command=test_print).pack(side="left")
        ttk.Button(buttons, text="Fertig", command=win.destroy).pack(side="right")


def run():
    if os.name != "nt":
        print("Diese GUI ist die Windows-Variante (tkinter). "
              "Unter Linux: setup-gui.sh bzw. setup_gui.py (GTK).")
        sys.exit(1)
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    try:
        icon = base_dir() / "icon.ico"
        if icon.exists():
            root.iconbitmap(str(icon))
    except Exception:
        pass

    # Windowed-EXE hat kein stdout/stderr – Fehler in After-Callbacks
    # landen statt dessen in der Log-Datei (statt lautlos zu sterben).
    def report_callback_exception(_exc_type, exc_value, _exc_tb):
        try:
            import traceback

            text = "".join(traceback.format_exception(_exc_type, exc_value, _exc_tb))
            win_backend.append_log_file("GUI-Callback-Fehler:\n" + text)
        except Exception:
            pass

    root.report_callback_exception = report_callback_exception
    try:
        win_backend.append_log_file("Setup-GUI gestartet.")
    except Exception:
        pass
    SetupWindow(root)
    root.mainloop()
    try:
        win_backend.append_log_file("Setup-GUI beendet.")
    except Exception:
        pass


if __name__ == "__main__":
    run()
