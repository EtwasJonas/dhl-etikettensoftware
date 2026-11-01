# Status & offene Aufgaben

> Agenten: **Diese Datei zuerst lesen** und nach erledigten Aufgaben aktualisieren
> (inkl. Datum). Letzte Aktualisierung: 2026-11-01.

## Aktueller Stand: Mint-Code fertig + Windows-11-Support implementiert, wartet auf echte Tests

`origin/main` = Siehe git log (Windows-Support als neuer Commit). Repo **öffentlich**.

### Windows 11 (neu, 01.11.2026)

- **Druck-Backend Windows**: `win_backend.py` – GDI-Rasterdruck via
  pypdfium2 (600 dpi) + Pillow ImageWin + win32print/win32ui; Papierformat
  aus Treiberliste gematcht (exakt → fuzzy), Orientation automatisch,
  Uniform-Scale-Einpassung in den druckbaren Bereich (Barcode-Scannbarkeit).
- **tkinter-Setup-GUI** (`setup_gui_win.py`): Drucker + Papierformat
  (Windows-API), Etikettengröße, Zuschnitt mm, Watch-Modus/Ordner/Filter,
  Marke-Position, Autostart-Checkbox; „✓ Bereits installiert“ mit
  Vorbefüllung + „Einstellungen aktualisieren“ + Deinstallieren;
  GUI-Kalibrierung (Variante 1/2/3/5/6, jeder Testdruck nur nach
  Bestätigung; Variante 4 = Ghostscript nur Linux).
- **Watcher** unter Windows: Einzelinstanz-Lock (kein Doppeldruck),
  Log nach `%LOCALAPPDATA%\dhl-label\dhl-label.log`, Autostart via
  Startmenü-Autostart-Verknüpfung (kein Admin nötig).
- **Auslieferung**: `dhl-label.exe` (PyInstaller onefile/windowed, Doppelklick
  = Setup-GUI), CI `windows-build.yml` baut bei jedem Push (Tests unter Linux
  **und** Windows), Release-Anhang bei Tag `v*`. requirements-windows.txt.
- **Tests**: `tests/test_core.py` (15 Tests: Parser, Config-Pfade, write_config
  BOM-frei, Crop/Compose-Geometrie inkl. Uniform-Scale-Assert + Ecken-Check
  via Contentstream, Namensfilter, fit_rect, Papier-Match, Windows-API-Probe).
  Lokal alle grün; GDI-Pipeline bis Treiber-DC lokal verifiziert
  (StartDoc-Ende bleibt Hardware-Test vorbehalten, "Microsoft Print to PDF"
  zeigt bei StartDoc einen modalen Dialog → nicht für Auto-Tests nutzbar).

### Mint/Linux (unverändert geblieben)

- `setup_gui.py`: GTK3-Formular → install.sh → Log-Streaming → Erfolgsmeldung
  → GUI-Kalibrierdialog; Installations-Erkennung, Deinstallieren-Knopf.
  GUI-Kalibrierung nutzt jetzt `gh.default_config_path()`-kompatible
  Signaturen (`installed_state(path)` etc.) – Verhalten identisch.
- Windows-Tests grün: py_compile aller Python-Dateien, bash -n, GUI-Logik-Tests.

## Nächster Schritt: Echte Tests

1. **Mint-PC** (vom Nutzer, Agent begleitet): ZIP laden → setup-gui.sh →
   Kalibrierung mit echter DHL-PDF → Alltags-Check. Details wie unten.
2. **Windows-11-PC**: EXE aus GitHub Release laden (oder lokal gebaute
   `dist/dhl-label.exe`) → Doppelklick → Vretti per USB verbinden → Setup
   durchlaufen → Kalibrierung → Alltags-Check (PDF herunterladen → druckt).

### Offene Punkte, die dabei vom Nutzer zu klären sind

- Mint: `lpstat`-Ausgaben, Kalibrier-Variante, Namensfilter vs. echter
  Dateiname, ggf. `rotate = 270`
- Windows: Papierformat-Name des Vretti-Treibers (GUI listet ihn vor),
  Kalibrier-Variante, falls Marke verkehrt herum: `rotate = 270`

## Bekannte Restrisiken

1. CUPS-Medianame des Vretti (Mint-GUI liest ihn vor, Nutzer bestätigt).
2. Windows: Vretti-Treiber muss das Papierformat 100×150 melden – sonst
   Treiber-Standard (Hinweis steht im Log; im Treiber „Druckereinstellungen“
   benutzerdefiniertes Format anlegen).
3. pkexec-Passwortdialog im GUI-Kontext (polkit) – falls er nicht erscheint,
   Terminal-Fallback `bash install.sh` dokumentiert.
4. Windows: SmartScreen-Warnung beim ersten Start der EXE („Trotzdem
   ausführen“) – dokumentiert im README.

## Aktive Codetasks: keine

Sobald Hardware-Tests Feedback liefern (Kalibriernummer, Fehlermeldungen,
`dhl-label.log` bzw. `journalctl --user -u dhl-label`), gezielt fixen.
**Wichtig**: Uniform-Scale-Assert nicht brechen (Barcode-Scannbarkeit,
docs/architektur.md §8.3) und Testdruck-Bestätigungen beibehalten.

## Historie (alle gepusht)

- `a3208a0` Erstversion: CLI-Installer, Watcher, Crop (obere Hälfte), lp-Druck
- `a6310cb` `.gitattributes` LF-Erzwingung
- `3fff6ba` Review-Bugfixes: calibrate-Overrides, gs-Arg-Reihenfolge, Retry-Grenze
  (`fehlgeschlagen/`), Namensfilter `versand|dhl|paket`, Druckerwahl-Validierung
- `261d172` USB+WLAN-Druckerwahl (Statusanzeige, `printers`-Befehl mit Geräte-URIs)
- `84ed979` README: ZIP-Download-Link + 3-Schritte-Anleitung
- `a3655a4` Zielgrößen-Anpassung (compose: rotate+scale auf 100×150), 6
  Kalibriervarianten mit Bestätigung, Mediengrößen-Erklärtext
- `051cb70` GUI-Setup-Assistent: GTK3-Erstinstallation ohne Terminal + Tests
- `476e0e3` install.sh: systemd-Dienst beim Setup neu starten (erneutes Einrichten
  übernimmt frische config.conf sofort)
- `c912103` GUI: Installations-Erkennung + DHL-Icon (Banner, Vorbefüllung,
  „Einstellungen aktualisieren", icon.png für Fenster und Desktop-Einträge)
- `448830b` GUI: Deinstallieren-Knopf (Bestätigung, Live-Ausgabe, Zustands-Refresh;
  uninstall.sh wird nach APP_DIR kopiert)
- `429545c` Stand vor Windows-Support (public-Repo-Umstellung)
- Windows-Support (01.11.2026): win_backend.py (GDI-Druck, Autostart, Lock),
  setup_gui_win.py (tkinter), tests/test_core.py, CI-Workflow + PyInstaller-EXE,
  README/Docs Windows-Kapitel
