#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_gui_win.py – Setup-Assistent für Windows 11 (tkinter).

GTK3/PyGObject ist unter Windows nicht praktikabel; tkinter ist in der
Windows-Python-Installation enthalten und wird von PyInstaller gebündelt.

Ablauf:
  1) Formular: Profil („Standard“ = Werks-Kalibrierung; eigene Profile
     speicherbar/wechselbar/löschbar), Drucker, Papierformat
     (Windows-Treiber), Etikettengröße, Zuschnitt, Watch-Modus (Downloads
     mit Namensfilter oder eigener Ordner), Position der Marke im A4-PDF,
     Autostart
  2) „Einrichten“ → schreibt %APPDATA%/dhl-label/config.conf, richtet die
     Autostart-Verknüpfung im Startmenü-Autostart-Ordner ein (kein Admin
     nötig) und startet einen laufenden Watcher mit den neuen Werten neu
  3) „Manuell drucken…“ → druckt die neueste passende DHL-PDF mit den
     gespeicherten Einstellungen (z.B. falls der Watcher nicht läuft oder
     eine PDF in fehlgeschlagen/ gelandet ist)
  4) Watcher-Knopf zeigt jederzeit den Status (läuft/gestoppt, mit PID)

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
        self._watcher_state = None
        self._profiles = {}        # {name: werte} aus der config.conf
        self._active_profile = ""  # aktuell gewähltes Profil

        self._build_ui()
        ok, problems = gh.check_environment()
        if not ok:
            self._log("Voraussetzungen fehlen:")
            for problem in problems:
                self._log("  - " + problem)
        self.refresh_state()
        self.load_printers_async()
        self._update_watcher_button()

    # ------------------------------------------------------------ UI-Aufbau

    def _build_ui(self):
        # Tk-Variablen zuerst (keine Walrus-Zuweisungen auf Attribute möglich)
        _def = gh.load_defaults()
        self.printer_var = tk.StringVar()
        self.paper_var = tk.StringVar()
        self.target_var = tk.StringVar(
            value=_def.get("target_size_mm") or "100x150")
        self.trim_top_var = tk.StringVar(value=_def.get("trim_top_mm") or "0")
        self.trim_bottom_var = tk.StringVar(value=_def.get("trim_bottom_mm") or "0")
        self.trim_left_var = tk.StringVar(value=_def.get("trim_left_mm") or "0")
        self.trim_right_var = tk.StringVar(value=_def.get("trim_right_mm") or "0")
        self.watch_mode_var = tk.StringVar(value="downloads")
        self.watch_dir_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.pattern_var = tk.StringVar(value=DEFAULT_PATTERN)
        self.side_var = tk.StringVar(value="top")
        self.autostart_var = tk.BooleanVar(value=True)
        self.profile_var = tk.StringVar()

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

        # Profil
        add_label("Profil:", row, bold=True)
        prof_frame = ttk.Frame(form)
        prof_frame.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
        self.profile_combo = ttk.Combobox(prof_frame, state="readonly",
                                          textvariable=self.profile_var, width=26)
        self.profile_combo.pack(side="left")
        self.profile_combo.bind("<<ComboboxSelected>>", self.on_profile_selected)
        self.profile_new_btn = ttk.Button(prof_frame, text="Als neues Profil…",
                                          command=self.new_profile, width=16)
        self.profile_new_btn.pack(side="left", padx=(8, 0))
        self.profile_del_btn = ttk.Button(prof_frame, text="Löschen",
                                          command=self.delete_profile_clicked,
                                          width=10)
        self.profile_del_btn.pack(side="left", padx=(8, 0))
        self._action_buttons.append(self.profile_new_btn)
        self._action_buttons.append(self.profile_del_btn)
        row += 1
        ttk.Label(form, text="„Standard“ = Werks-Kalibrierung (verifizierte Werte). "
                             "Profil wechseln lädt dessen Werte (Etikettengröße, "
                             "Zuschnitt, Position der Marke) – übernehmen mit "
                             "„Einrichten“ / „Einstellungen aktualisieren“.",
                  wraplength=560, foreground="#555").grid(row=row, column=1,
                                                          columnspan=2,
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
        self.print_manual_btn = ttk.Button(buttons, text="Manuell drucken…",
                                           command=self.manual_print)
        self.print_manual_btn.pack(side="left", padx=(8, 0))
        self._action_buttons.append(self.print_manual_btn)
        self.start_btn = ttk.Button(buttons, text="Watcher: Status wird geprüft …",
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

    # ------------------------------------------------------------ Profile

    def _set_form_values(self, values):
        """Etikettengröße + Zuschnitt + Position aus Profil-Werten ins Formular."""
        self.target_var.set((values.get("target_size_mm") or "").strip())
        for var, key in ((self.trim_top_var, "trim_top_mm"),
                         (self.trim_bottom_var, "trim_bottom_mm"),
                         (self.trim_left_var, "trim_left_mm"),
                         (self.trim_right_var, "trim_right_mm")):
            raw = (values.get(key) or "0").replace(",", ".")
            try:
                value = float(raw)
            except ValueError:
                value = 0.0
            var.set(f"{value:g}")
        self.side_var.set("bottom" if (values.get("side") or "").lower() == "bottom"
                          else "top")

    def _set_profile_choices(self, selected):
        """Profil-Dropdown füllen; Auswahl = selected (oder leer = kein Profil)."""
        names = list(self._profiles.keys())
        self.profile_combo.configure(values=names)
        self.profile_var.set(selected if selected in self._profiles else "")

    def on_profile_selected(self, _event=None):
        """Anderes Profil gewählt: dessen Werte ins Formular laden (nicht
        speichern – das passiert über „Einrichten“/„Einstellungen aktualisieren“)."""
        if self.busy:
            return
        name = self.profile_var.get().strip()
        if name and name in self._profiles:
            self._active_profile = name
            self._set_form_values(self._profiles[name])
            self._log(f"Profil „{name}“ geladen – übernehmen mit "
                      "„Einrichten“ bzw. „Einstellungen aktualisieren“.")

    def _current_profile_values(self, trim_top, trim_bottom, trim_left, trim_right,
                                target_text):
        """Profil-Werte aus dem Formular (fürs Speichern/Aktualisieren)."""
        return {
            "side": self.side_var.get(),
            "trim_top_mm": f"{trim_top:g}",
            "trim_bottom_mm": f"{trim_bottom:g}",
            "trim_left_mm": f"{trim_left:g}",
            "trim_right_mm": f"{trim_right:g}",
            "target_size_mm": target_text,
            "rotate": "auto",  # Rotation wird in der GUI immer auf auto gesetzt
        }

    def new_profile(self):
        """Aktuelle Formular-Werte als neues Profil speichern und aktiv setzen
        (läuft über „Einrichten“ → Config + Watcher-Neustart)."""
        if self.busy:
            return
        from tkinter import simpledialog

        name = simpledialog.askstring(
            "Neues Profil",
            "Name des neuen Profils\n(z.B. „Zweit-PC“ oder „Testwerte“):",
            parent=self.root)
        if not name:
            return
        name = name.strip()
        if name.lower() == gh.FACTORY_PROFILE.lower():
            messagebox.showerror(
                "Neues Profil",
                "„Standard“ ist das Werks-Profil – es ist immer vorhanden und "
                "kann nicht neu angelegt werden. Um die Werks-Werte zu ändern: "
                "Profil „Standard“ auswählen, Werte anpassen und "
                "„Einstellungen aktualisieren“ klicken.")
            return
        if not gh.valid_profile_name(name):
            messagebox.showerror(
                "Neues Profil",
                "Bitte einen Namen mit höchstens 40 Zeichen ohne [ ] : = verwenden.")
            return
        if any(name.lower() == existing.lower() for existing in self._profiles):
            messagebox.showerror(
                "Neues Profil",
                f"Profil „{name}“ gibt es schon.\n\nProfil oben auswählen und "
                "„Einstellungen aktualisieren“ klicken, um es mit den "
                "angezeigten Werten zu überschreiben.")
            return
        self.profile_var.set(name)
        self.save()

    def delete_profile_clicked(self):
        """Gewähltes (nicht-Werks-)Profil aus der config.conf entfernen."""
        if self.busy:
            return
        name = self.profile_var.get().strip()
        if not name:
            messagebox.showerror("Profil löschen",
                                 "Bitte zuerst ein Profil auswählen.")
            return
        if name == gh.FACTORY_PROFILE:
            messagebox.showerror(
                "Profil löschen",
                "Das Werks-Profil „Standard“ kann nicht gelöscht werden.\n\n"
                "Seine Werte kannst du ändern: Profil „Standard“ auswählen, "
                "Werte anpassen, „Einstellungen aktualisieren“ klicken.")
            return
        config_path = gh.default_config_path()
        if not config_path.exists():
            messagebox.showerror("Profil löschen",
                                 "Es gibt noch keine gespeicherten Einstellungen.")
            return
        if not messagebox.askyesno(
                "Profil löschen",
                f"Profil „{name}“ wirklich löschen?\n\nDie Werte im Formular "
                "bleiben unverändert."):
            return
        try:
            removed = gh.delete_profile(config_path, name)
        except Exception as exc:
            messagebox.showerror("Profil löschen", str(exc))
            return
        if not removed:
            messagebox.showerror(
                "Profil löschen",
                f"Profil „{name}“ war nicht in den Einstellungen gespeichert.")
            return
        self._profiles.pop(name, None)
        if self._active_profile == name:
            self._active_profile = ""
        self._set_profile_choices("")
        self._log(f"Profil „{name}“ gelöscht – Formular unverändert.")

    # ------------------------------------------------------------ Zustand

    def refresh_state(self):
        installed, cfg = gh.installed_state()
        self.installed_cfg = cfg if installed else None
        if installed:
            self._profiles, active = gh.read_profiles()
            values, selected, hinweis = gh.resolve_startup_values(
                cfg, self._profiles, active)
            self._active_profile = selected
            self.banner.configure(
                text=f"✓ Bereits installiert – Profil: {selected or '(keins)'}",
                foreground="#1a7f37")
            self.save_btn.configure(text="Einstellungen aktualisieren")
            self.uninstall_btn.pack(side="right")
            self.printer_var.set(cfg.get("printer", ""))
            self.paper_var.set(cfg.get("media", ""))
            self.watch_mode_var.set(
                "downloads" if cfg.get("watch_mode", "downloads") == "downloads"
                else "custom")
            self.watch_dir_var.set(cfg.get("watch_dir")
                                   or str(Path.home() / "Downloads"))
            self.pattern_var.set(cfg.get("filename_pattern") or DEFAULT_PATTERN)
            self._set_profile_choices(selected)
            self._set_form_values(values)
            if hinweis:
                self._log("Hinweis: " + hinweis)
        else:
            self._profiles, _active = gh.read_profiles()  # → nur „Standard“
            self._active_profile = gh.FACTORY_PROFILE
            self._set_profile_choices(gh.FACTORY_PROFILE)
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
            trim_top = gh.parse_trim_mm(self.trim_top_var.get())
            trim_bottom = gh.parse_trim_mm(self.trim_bottom_var.get())
            trim_left = gh.parse_trim_mm(self.trim_left_var.get())
            trim_right = gh.parse_trim_mm(self.trim_right_var.get())
        except ValueError as exc:
            messagebox.showerror("Fehler", str(exc))
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

        profile_name = self.profile_var.get().strip()
        profiles = dict(self._profiles)
        if profile_name:
            # Gewähltes Profil mit den Formular-Werten synchronisieren
            profiles[profile_name] = self._current_profile_values(
                trim_top, trim_bottom, trim_left, trim_right, target_text)
        # Manuell gepflegte lp-Extra-Optionen nicht verschlucken
        extra_options = (self.installed_cfg or {}).get("extra_options") or ""

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
                    trim_right_mm=trim_right,
                    extra_options=extra_options,
                    profile=profile_name,
                    profiles=profiles)
                self._profiles = profiles
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
                else:
                    win_backend.spawn_watch_detached()
                    self._ui(self._log,
                             "Watcher lief nicht → jetzt gestartet "
                             "(ob er bei jeder Anmeldung startet, regelt die Autostart-Option oben).")
                self._ui(self._log, "Fertig – ab jetzt wird automatisch gedruckt.")
                self._ui(self.refresh_state)
                self._ui(self._ask_manual_print)
            except Exception as exc:
                self._ui(self._log, f"Fehler beim Einrichten: {exc}")
                self._ui(lambda: messagebox.showerror("Fehler", str(exc)))
            finally:
                self._ui(self._set_busy, False)
        threading.Thread(target=work, daemon=True).start()

    def _ask_manual_print(self):
        if messagebox.askyesno(
                "Einrichten abgeschlossen",
                "Die Einstellungen sind gespeichert.\n\n"
                "Jetzt eine DHL-Marke manuell drucken? (braucht eine passende "
                "DHL-PDF im Watch-Ordner – sonst kannst du eine Datei auswählen.)"):
            self.manual_print()

    # ------------------------------------------------------------ Manueller Druck

    def manual_print(self):
        """Druckt die neueste passende DHL-PDF mit den GESPEICHERTEN
        Einstellungen (inkl. Zuschnitt/Etikettengröße) – für den Fall, dass
        der Watcher gerade nicht druckt oder eine PDF in fehlgeschlagen/
        gelandet ist. Gibt es nichts Passendes, darf eine Datei gewählt werden."""
        if self.busy:
            return
        config_path = gh.default_config_path()
        if not config_path.exists():
            messagebox.showerror(
                "Manueller Druck",
                "Bitte zuerst „Einrichten“ – es gibt noch keine gespeicherten "
                "Einstellungen.")
            return
        try:
            cfg = dhl_label.Config(config_path)
        except SystemExit as exc:
            messagebox.showerror("Manueller Druck", str(exc))
            return
        probe = SimpleNamespace(watch_mode=cfg.watch_mode,
                                filename_pattern=cfg.filename_pattern)
        src = dhl_label.newest_matching(cfg.watch_dir, probe)
        if src is None:
            failed_dir = Path(cfg.watch_dir) / "fehlgeschlagen"
            if failed_dir.is_dir():
                src = dhl_label.newest_matching(failed_dir, probe)
                if src is not None:
                    self._log(f"Keine PDF im Watch-Ordner – nehme die neueste "
                              f"aus fehlgeschlagen/: {src.name}")
        if src is None:
            src = filedialog.askopenfilename(
                title="DHL-PDF für den manuellen Druck wählen",
                initialdir=str(cfg.watch_dir),
                filetypes=[("PDF-Dateien", "*.pdf"), ("Alle Dateien", "*.*")])
            if not src:
                return
        src = Path(src)
        if not messagebox.askyesno(
                "Manueller Druck",
                f"Jetzt drucken?\n\n"
                f"Datei: {src.name}\n"
                f"Drucker: {cfg.printer}\n\n"
                "(Es gelten die gespeicherten Einstellungen – inkl. "
                "Zuschnitt und Etikettengröße.)"):
            return
        self._set_busy(True)
        self._log(f"Manueller Druck: {src.name} an Drucker {cfg.printer!r} …")

        def work():
            try:
                tmp = Path(tempfile.gettempdir()) / (src.stem + ".manual.pdf")
                try:
                    dhl_label.make_cropped(src, tmp, cfg)
                except Exception as exc:
                    self._ui(self._log, f"Aufbereitung fehlgeschlagen: {exc}")
                    self._ui(lambda: messagebox.showerror(
                        "Manueller Druck",
                        f"Aufbereitung fehlgeschlagen:\n{exc}\n\n"
                        "(Datei beschädigt oder noch im Download? Einen Moment "
                        "warten und erneut versuchen.)"))
                    return
                ok = dhl_label.print_pdf(tmp, cfg)
                try:
                    tmp.unlink()
                except OSError:
                    pass
                if ok:
                    self._ui(self._log, "Gedruckt – Etikette beschriften!")
                    moved = self._move_processed(src, cfg)
                    if moved:
                        self._ui(self._log, f"PDF verschoben nach: {moved} "
                                 "(verhindert Doppeldruck)")
                    self._ui(lambda: messagebox.showinfo(
                        "Manueller Druck", "Das Etikett wurde an den Drucker "
                        "übergeben."))
                else:
                    self._ui(self._log,
                             "Druck fehlgeschlagen – den Grund siehst du in der "
                             "Log-Datei: %LOCALAPPDATA%\\dhl-label\\dhl-label.log "
                             "(mit Zeitstempeln).")
                    self._ui(lambda: messagebox.showerror(
                        "Manueller Druck",
                        "Der Druck ist fehlgeschlagen.\n\nGrund: Log-Datei "
                        "%LOCALAPPDATA%\\dhl-label\\dhl-label.log öffnen "
                        "(letzte Zeilen mit [Datum Uhrzeit])."))
            finally:
                self._ui(self._set_busy, False)
        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _move_processed(src, cfg):
        """Verschiebt eine erfolgreich manuell gedruckte PDF nach gedruckt/
        (gleiche Semantik wie der Watcher → kein Doppeldruck), wenn sie im
        Watch-Ordner oder in fehlgeschlagen/ liegt. → Zielpfad oder None."""
        watch = Path(cfg.watch_dir)
        failed = watch / "fehlgeschlagen"
        src = Path(src)
        try:
            in_watch = src.parent == watch
            in_failed = src.parent == failed
            if not (in_watch or in_failed):
                return None
            target_dir = watch / cfg.processed_dirname
            target_dir.mkdir(exist_ok=True)
            target = target_dir / src.name
            src.replace(target)
            return target
        except OSError:
            return None

    # ------------------------------------------------------------ Watcher

    def _update_watcher_button(self):
        """Hält den Watcher-Knopf auf dem aktuellen Stand (alle 3 Sekunden),
        damit man ohne Klick sieht, ob er läuft. Landet die Aktualisierung
        mitten in einer Aktion (busy), wird nur der nächste Tick geplant."""
        if not self.busy:
            running, pid = win_backend.watcher_running()
            state = (bool(running), pid if running else None)
            if state != self._watcher_state:
                self._watcher_state = state
                if running:
                    self.start_btn.configure(
                        text=f"Watcher läuft (PID {pid}) – neu starten")
                else:
                    self.start_btn.configure(
                        text="Watcher läuft nicht – jetzt starten")
        self.root.after(3000, self._update_watcher_button)

    def start_watcher_now(self):
        if self.busy:
            return
        running, pid = win_backend.watcher_running()
        if running:
            if not messagebox.askyesno(
                    "Watcher neu starten",
                    f"Der Watcher läuft bereits (PID {pid}).\n\n"
                    "Neu starten? Er übernimmt dann die gespeicherten "
                    "Einstellungen (z.B. nach Änderungen nötig)."):
                return
            action = "restart"
        else:
            if not gh.default_config_path().exists():
                messagebox.showerror(
                    "Watcher starten",
                    "Es gibt noch keine gespeicherten Einstellungen.\n\n"
                    "Bitte zuerst „Einrichten“ klicken – erst dann hat der "
                    "Watcher Drucker und Zuschnitt-Werte, mit denen er drucken kann.")
                return
            action = "start"
        self._set_busy(True)
        self._log("Watcher wird gestartet …" if action == "start"
                  else "Watcher wird neu gestartet …")

        def work():
            try:
                if action == "restart":
                    win_backend.kill_watcher()
                win_backend.spawn_watch_detached()
                self._ui(self._log,
                         "Watcher gestartet – Status sieht du am Knopf "
                         "(aktualisiert sich alle 3 Sekunden).")
            except Exception as exc:
                self._ui(self._log, f"Watcher konnte nicht gestartet werden: {exc}")
                self._ui(lambda: messagebox.showerror("Fehler", str(exc)))
            finally:
                self._ui(self._set_busy, False)
        threading.Thread(target=work, daemon=True).start()

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
