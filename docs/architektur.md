# Architektur & Technische Details

## 1. Datei-Zuständigkeiten

| Datei | Rolle |
|---|---|
| `dhl_label.py` | Kern-CLI: `watch` `print` `print-latest` `crop` `calibrate` `show-config` `printers` `print-pdf`. Crop/Dreh/Skalier-Logik (pypdf), lp-Druck, Watcher-Loop. **Kein** GUI-Code. |
| `gui_helpers.py` | Pure Logik ohne GTK (Windows-testbar): `list_printers`, `media_sizes`, `parse_size_mm`, `parse_trim_mm`, `build_install_cmd`, `calibration_variants`, `build_crop_cmd`, `build_print_cmd`, `check_environment`, `write_config_file`, `read_installed_config`, `installed_state` (Erkennung bestehender Installation für die GUI). |
| `icon.png` | Fenster-/Desktop-Icon der GUI und der Desktop-Einträge. |
| `setup_gui.py` | GTK3-Setup-Assistent (Formular → install.sh-Flags → Log-Streaming → Erfolg → GUI-Kalibrierdialog; Installations-Erkennung mit Vorbefüllung, Deinstallieren-Knopf). Zuschnitt-Felder (mm oben/unten/links/rechts) im Formular und im Kalibrier-Dialog inkl. „Werte speichern“ (schreibt config.conf via `write_config_file` + `systemctl --user restart dhl-label` – Feintuning ohne Installer-Lauf). Läuft mit **System-Python** (`/usr/bin/python3`), nicht im venv (GTK liegt im System, pypdf im venv). |
| `setup-gui.sh` | Doppelklick-Launcher für die GUI (`exec /usr/bin/python3 "$(dirname "$0")/setup_gui.py"`); braucht einmalig exec-Bit nach ZIP-Entpacken. |
| `install.sh` | Installer, zwei Modi: interaktiv (kein Argument, Terminal-Fallback) und nicht-interaktiv per Flags (GUI ruft auf): `--printer --media --target --trim-top --trim-bottom --trim-left --trim-right --watch-mode downloads|custom --watch-dir --pattern --side top|bottom --no-calibrate --pkexec --non-interactive`. Im Nicht-interaktiv-Modus Pflicht-Flags validieren (sonst würde read hängen); Zuschnitt-Werte werden (in beiden Modi) normalisiert (Komma→Punkt, leer=0) und gegen Zahlen-Regex geprüft, bevor installiert wird. |
| `uninstall.sh` | Entfernt Service, Dateien, Icons, Config. Wird von install.sh zusätzlich nach APP_DIR kopiert (GUI kann aus installierter Kopie deinstallieren). |
| `dhl-label.service` | systemd-User-Unit, `ExecStart=%h/.local/bin/dhl-label watch`, `Restart=on-failure`, `WantedBy=default.target`. |
| `win_backend.py` | Windows-Backend: GDI-Druckpfad (pypdfium2 + Pillow + win32print/win32ui), Drucker-/Papierformate, Autostart-Verknüpfung, Watcher-Lock, Log-Datei. Top-Level nur Stdlib (auch unter Linux importierbar). |
| `setup_gui_win.py` | Windows-Setup-Assistent (tkinter): Formular → config.conf direkt schreiben → Autostart-Verknüpfung → Manueller Druck (gespeicherte Einstellungen, inkl. fehlgeschlagen/-Fallback) → Watcher-Knopf mit Live-Status (3-s-Refresh). |
| `dhl-label-win.spec` | PyInstaller-Spec → `dist/dhl-label.exe` (onefile, windowed, icon.ico). |
| `defaults.conf` | Werks-Kalibrierung (verifiziert am SN 420B): side/trims/target_size_mm/rotate. Werden von allen Setups als Vorbefüllung gelesen (Windows-GUI, GTK-GUI, install.sh); EXE bündelt die Datei. Bestehende config.conf bleiben unangetastet. |
| `.github/workflows/windows-build.yml` | CI: Tests (Linux+Windows), EXE-Build, Release-Anhang bei Tag `v*`. |
| `tests/test_core.py` | Minimale Test-Suite (`python tests/test_core.py`), plattformunabhängig. |
| `README.md` | Nutzer-Doku (Download-Link der ZIP, 3-Schritte-Installation, Befehle, Kalibrierung, Fehlersuche). |

## 2. Verarbeitungs-Kette (Herzstück)

1. **Crop** (`_crop_region`): obere/untere/voll per `side`; `trim_top_mm`/`trim_bottom_mm` schneiden im Bereich nach; Koordinaten in pt, `MM_TO_PT = 72/25.4`.
2. **Compose** (`compose_target`, aktiv wenn `target_size_mm` gesetzt): 
   - `cropbox` setzen → `add_page` → Inhalt via `Transformation().translate(-l,-b)` an Ursprung, `mediabox`/`cropbox` = Region
   - Rotation: `rotate = auto` → 90° wenn (Crop quer) ≠ (Ziel quer); bake via `p.rotation = 90; transfer_rotation_to_content()`
   - **Uniform scale** `s = min(tw/w, th/h)` – NIE beide Achsen unabhängig! Danach zentrieren (`tx = (tw-w*s)/2` etc.), finale Box = exakt Zielgröße.
   - pypdf-Details: `add_transformation` ändert nur den Content, Boxen manuell setzen; cropbox braucht `RectangleObject([float,...])`.
3. **Druck** (`print_pdf`): `lp -d <printer> -o media=<media> [<extra_options>] <pdf>`; lp-Fehler nie Watcher crashen lassen (`except OSError`).
4. **Watch-Ordner** (`watch`): Polling alle `poll_seconds` (2 s), Download-Abchluss = Größe stabil zwischen zwei Polls; Namensfilter nur im downloads-Modus (`versand|dhl|paket`, case-insensitive Regex); Startup-Snapshot überspringt bestehende PDFs (außer `--process-existing`); Erfolg → `gedruckt/`, 3 Druckfehler → `fehlgeschlagen/`.

## 3. Config-Format (`~/.config/dhl-label/config.conf`, BOM-frei!)

```ini
[printer]
name = <CUPS-Druckername>
media = <CUPS-Mediengröße, z.B. 4x6>
extra_options =            # zusätzliche lp-Optionen (shlex-split)

[crop]
side = top                 # top | bottom | full
trim_top_mm = 0.0
trim_bottom_mm = 0.0
trim_left_mm = 0.0         # mm, die zusätzlich weggeschnitten werden (Kalibrierung)
trim_right_mm = 0.0
page_index = 0             # 0 = erste Seite
use_ghostscript = false    # GS-Hardcrop statt pypdf
target_size_mm = 100x150   # leer/0 = nur croppen (kein compose)
rotate = auto              # auto | 0 | 90 | 270

[watch]
mode = downloads           # downloads (mit Filter) | custom (alle PDFs)
dir = /home/USER/Downloads
filename_pattern = versand|dhl|paket
processed_dirname = gedruckt
poll_seconds = 2.0
process_existing = false
```

Parsing: `ConfigParser` + `SectionProxy`-Fallback (Fehlen von Sections ist OK,
getestet). Env-Override für Tests: `DHL_LABEL_CONFIG`.

## 4. Instanz-Layout auf dem Ziel-PC (Mint)

```
~/.local/share/dhl-label/          # venv (pypdf), dhl_label.py, gui_helpers.py, setup_gui.py
~/.local/bin/dhl-label             # Wrapper → venv-Python dhl_label.py
~/.local/bin/dhl-label-setup       # Wrapper → /usr/bin/python3 setup_gui.py (GTK!)
~/.config/dhl-label/config.conf
~/.config/systemd/user/dhl-label.service
~/.local/share/applications/dhl-label-print.desktop    # „DHL-Marke drucken“ (print-latest)
~/.local/share/applications/dhl-label-setup.desktop    # „DHL-Setup“ (GUI)
/tmp bzw. ~/.cache                 # Kalibrier-Zwischen-PDFs
```

Bewusste Trennung: **venv-Python** hat pypdf, aber kein GTK; **System-Python**
hat GTK (Mint/Cinnamon-Abhängigkeit `python3-gi`, `gir1.2-gtk-3.0`), aber kein
pypdf. GUI-Kalibrierung deshalb: Crop via `venv/bin/python dhl_label.py crop …`
(Flags!) + Druck via `lp` direkt – beide terminal-frei, Output in GUI-Fenster.
GUI-Kalibriervarianten inkl. Variante 4 mit `--target ""` (GS ohne compose).

## 5. install.sh – zwei Modi

- Ohne Flags: wie bisher interaktiv (Fragen zu Drucker/Medium/Etikettengröße/
  Zuschnitt/Watch-Modus/Side), mit Einsteiger-Erklärtexten.
- Mit Flags: `--pkexec` für apt (GUI-Passwortdialog), `--non-interactive`
  verhindert JEDES `read` (Pflicht-Flags werden vorher validiert, sonst `die`).
  `--target ""` (leer) ist erlaubt = nur croppen; in `--non-interactive` darf der
  leere Wert NICHT zum interaktiven Prompt führen (Bedingung: `-n FLAG_TARGET || NONINTERACTIVE`).
  Die vier Zuschnitt-Flags (`--trim-*`) sind optional (Default 0); GUI übergibt
  sie immer (validiert via `parse_trim_mm`).

## 6. Windows-Test-Werkzeuge (Entwickler-PC)

- **Test-venv** (seit Windows-Support): `$env:TEMP\opencode\wenv` mit pypdf,
  pywin32, pypdfium2, Pillow, pyinstaller → `& "$env:TEMP\opencode\wenv\Scripts\python.exe" …`
  (PYTHONPATH/pylibs reicht für pywin32 nicht – DLL-Suche seit Python 3.8).
- pypdf in `$env:TEMP\opencode\pylibs` (PYTHONPATH setzen).
- Test-A4: `PdfWriter(); add_blank_page(width=595.28, height=841.89)`; PDF **mit Inhalt**:
  blank page + `page.replace_contents(DecodedStreamObject mit set_data(b"...re f"))`.
- BOM-freies Schreiben von Testscripts: `[IO.File]::WriteAllText(path, text, [System.Text.UTF8Encoding]::new($false))`.
- Config für Tests: `$env:DHL_LABEL_CONFIG` → Temp-Pfad, BOM-frei!
- Bash: `C:\Program Files\Git\bin\bash.exe` (`-n` Syntaxcheck, `install.sh --help` testbar ohne apt).
- lp/gs existieren nicht unter Windows → `print_pdf` nutzt GDI-Backend (win_backend); Watcher-Test
  mit Druckfehlern prüft Retry-Logik (unverändert).
- **GUI-Smoke ohne Fenster**: tkinter-GUI-Konstruktor bauen + `root.destroy()`
  (kein mainloop) – tkinter ist anders als GTK unter Windows voll testbar.
- **EXE-Tests**: PyInstaller windowed-EXE wartet in PowerShell nicht →
  `Start-Process -Wait -PassThru` nutzen; Prozesse mit `Stop-Process -Name
  dhl-label` beenden (onefile-Parent überlebt `-Id` nicht umgekehrt: `-Id`
  tötet nur den Bootloader, das Child läuft weiter!).
- **"Microsoft Print to PDF" hängt bei StartDoc** (modaler Speichern-Dialog,
  PORTPROMPT) → GDI-Pipeline nur bis `CreateDC`/`Dib.draw` + `AbortDoc`
  testen; echten `EndDoc` nur am realen Drucker (Vretti) testen.
- Contentstream-Analyse: pypdf prependet jede `add_transformation` – die
  effektive Punkt-Abbildung komponiert man in **umgekehrter** Stream-Reihenfolge
  (PDF-Row-Vektoren: letzter `cm` wirkt zuerst).

## 7. Fehler- & Robustheitsregeln

- lp-Fehler: nie Crash, `fehlgeschlagen/`-Ordner nach 3 Versuchen.
- Watcher überlebt Crop-Fehler und verschwundene Dateien (Stale-Cleanup).
- ZIP-GitHub-Download verliert exec-Bits → README sagt `bash install.sh` (statt `./install.sh`).
- `.gitattributes` erzwingt LF (Shell-Dateien müssen auf Linux laufen).
- Keine BOMs in Python/Config-Dateien (UTF-8 ohne BOM).

## 8. Minimal-Test-Suite (vor Push, docs/status.md §Tests)

1. `py_compile` aller Python-Dateien; `bash -n` aller Shell-Dateien.
2. Parser-Tests für `gui_helpers` mit vorbereiteten lpstat/lpoptions-Strings.
3. Compose-Geometrie auf Test-A4 (blank + content):
   - Zielseite exakt `283.46 × 425.20 pt` (100×150 mm) bzw. `287.9 × 432.0 pt` (101.6×152.4)
   - **Uniform-Scale-Assert**: finale CTM aus dem Output-Contentstream (alle `cm`
     in Reihenfolge multiplizieren) → `|a| == |d|` und `|b| == |c|` (Rotation) →
     keine Verzerrung (Barcode-Scannbarkeit!)
   - Inhalt der oberen Hälfte landet auf der Zielseite (Ecken-Check via CTM),
     Inhalt der unteren Hälfte ist weg (außerhalb der finalen Box)
4. Watcher-E2E: PDF in Watch-Ordner → erkannt → lp-Fehlerpfad → nach 3 Versuchen in `fehlgeschlagen/`.

   → Seit 11/2026 als `tests/test_core.py` umgesetzt (`python tests/test_core.py`,
   läuft plattformunabhängig und in CI unter Linux **und** Windows).

## 9. Windows-11-Unterstützung (seit 11/2026)

### 9.1 Neue Dateien

| Datei | Rolle |
|---|---|
| `win_backend.py` | Windows-Backend: GDI-Druckpfad, Drucker-/Papierformate via Druck-API, Autostart-Verknüpfung, Watcher-Lock, Log-Datei. Top-Level nur Standardbibliothek (auch unter Linux importierbar für Tests). |
| `setup_gui_win.py` | Setup-Assistent für Windows (tkinter; GTK3 ist unter Windows nicht praktikabel). Schreibt Config direkt, richtet Autostart ein, startet den Watcher nach „Einrichten“ automatisch (bzw. startet einen laufenden neu – kill_watcher wartet bis zum Prozess-Ende), Knopf „Manuell drucken…“ (neueste passende PDF mit gespeicherter Config drucken, Fallback fehlgeschlagen/, danach Verschieben nach gedruckt/), Watcher-Knopf mit Live-Status. Kalibriervarianten via CLI (`dhl-label calibrate`). |
| `dhl-label-win.spec` | PyInstaller-Spec → `dist/dhl-label.exe` (onefile, windowed, icon.ico). |
| `.github/workflows/windows-build.yml` | CI: Tests auf Linux + Windows, PyInstaller-Build, Upload-Artefakt, Release-Anhang bei Tag `v*`. |
| `requirements-windows.txt` | pypdf, pypdfium2, Pillow, pywin32. |
| `icon.ico` | Windows-Icon (aus icon.png generiert). |
| `tests/test_core.py` | Minimale Test-Suite (§8). |

### 9.2 Plattform-Verzweigungen in bestehendem Code

- `dhl_label.py`: `CONFIG_PATH = default_config_path()` (gui_helpers) –
  Windows: `%APPDATA%\dhl-label\config.conf`; env `DHL_LABEL_CONFIG` überschreibt
  weiterhin. `print_pdf` → nt: `win_backend.print_pdf_windows`, sonst `lp`.
  `main()` ohne Argument unter Windows → `cmd_setup` (Doppelklick = GUI);
  Unterbefehl `setup` nur auf Windows registriert. `log()` schreibt unter
  Windows zusätzlich nach `%LOCALAPPDATA%\dhl-label\dhl-label.log`
  (windowed-EXE hat kein stdout; `print` fängt das mit try/except ab).
- `gui_helpers.py`: `list_printers`/`media_sizes`/`check_environment` mit
  Windows-Dispatch; `installed_state`/`read_installed_config` defaulten auf
  `default_config_path()` (GTK-GUI übergibt expliziten Pfad – unverändert).
  Neu: `write_config_file` (BOM-frei, LF – gleiche Werte wie install.sh).

### 9.3 Druckpfad Windows (GDI-Raster, Hardware-verifiziert am SN 420B/Vretti)

1. gecroppte PDF (compose macht exakt Etikettengröße) → **Custom-Size-DEVMODE**:
   Bei gesetztem `target_size_mm` bekommt der Treiber `DMPAPER_USER` +
   `PaperWidth/PaperLength` (zehntel mm) = exakte Etikettengröße. Wichtig, weil
   Treiber-Vorgaben abweichen können (SN 420B „4 x 6" = 104,23 mm statt 101,6 →
   Inhalt säße ~1,3 mm versetzt). Fallback: Papierformat-Namensmatch
   (`cfg.media`, exakt → fuzzy) → Treiber-Standard.
2. **Render in druckernativer Auflösung** (`LOGPIXELSX`, SN 420B: 203 dpi) mit
   4× Übersampling → PIL BOX-Downsampling auf nativen Pixelraster →
   Schwellwert 170 auf Schwarz/Weiß (`render_pdf_thermal`): volle Striche,
   kein Grau-Dithering auf dem Thermokopf.
3. `CreateDC("WINSPOOL")` → `StartDoc/StartPage` → `PIL.ImageWin.Dib.draw`:
   Wenn Bild == Seitengröße (Normalfall) → **1:1 am Seitenursprung** (Druck ==
   PDF-Geometrie); sonst uniform in den druckbaren Bereich eingepasst
   (`fit_rect`), auf der physischen Seite zentriert (asymmetrische
   Treiberränder verschieben sonst). Fehler → False → Watcher-Retry (3×) →
   `fehlgeschlagen/` (identische Semantik wie lp).
4. "Microsoft Print to PDF" zeigt beim `StartDoc` einen modalen
   Speichern-Dialog (PORTPROMPT) – deshalb: lokaler Test nur bis `CreateDC` +
   `Dib.draw` + `AbortDoc`; echter Drucktest am realen Drucker.

**Verifizierte Kalibrierung (03.11.2026, SN 420B, 4"x6"-Rollen):**
DHL-Privatkunden-A4: Marke in Zeilen 24,17–123,74 mm, Spalten 9,74–199,22 mm,
Scheren-Linie 145,6–151,2 mm (Mittelfalz). Werte: `side = top`,
`trim_top_mm = 16.24`, `trim_bottom_mm = 16.66`, `trim_left_mm = 3.08`,
`trim_right_mm = 4.13`, `target_size_mm = 101.6x152.4`, `rotate = auto`.
Resultat (druckidentisch gemessen, 4×203 dpi + Schwelle 170): Rand
oben 5,00 / unten 5,13 mm, links/rechts je 13,39 mm, Inhalt 74,9×142,4 mm –
Schere weg, Uniform-Scale (Barcode scannbar), keine Verzerrung.

### 9.4 Watcher/Autostart unter Windows

- Einzelinstanz-Lock: `%LOCALAPPDATA%\dhl-label\watcher.lock` (PID +
  `OpenProcess`-Alive-Check) – zweiter `watch`-Start beendet sich sofort
  (verhindert Doppeldruck).
- Autostart = `.lnk` im Startmenü-Autostart-Ordner (kein Admin): Ziel = EXE
  (`watch`-Argument) bzw. `pythonw.exe dhl_label.py watch` im Dev-Fall.
  GUI-Checkbox steuert Anlegen/Entfernen; der Watcher-Knopf spawn't
  detached (`DETACHED_PROCESS`) – bei laufendem Watcher: Neustart mit
  Bestätigung; `kill_watcher()` wartet (bis 6 s), bis der Prozess wirklich
  weg ist, damit der Nachfolger den Lock nicht für „belegt“ hält. Nach
  „Einrichten“ läuft der Watcher automatisch (gestartet oder neu gestartet).
- Watcher-Knopf zeigt Live-Status („läuft (PID …)“/„läuft nicht“),
  GUI-interner 3-s-Timer (`_update_watcher_button`), pausiert bei `busy`.
- **Diagnose:** Log-Zeilen tragen `[YYYY-MM-DD HH:MM:SS]` (Datei-Log in
  `dhl_label._append_log_file` und `win_backend.append_log_file`). Der
  Watcher protokolliert beim Start die effektive Config (Drucker, Medium,
  Zielgröße, Zuschnitte) und warnt laut, wenn der konfigurierte Drucker
  in Windows nicht existiert (häufigste Ursache für
  fehlgeschlagen/-Landungen nach Config-Kopierverschieben).
- **Retry-Pause:** nach einem Druckfehler wartet der Watcher 10 s
  (`RETRY_DELAY`), bevor der nächste Versuch startet (früher: nächster
  Poll ≈ 4 s) – gibt AV-Scans/warm werdenden Druckern Zeit; erst nach
  3 Fehlversuchen wandert die PDF nach `fehlgeschlagen/`.
- Konfigurationidentisch zur Linux-Struktur; `processed_dirname = gedruckt`
  etc. funktionieren unverändert (pathlib).

### 9.5 EXE & CI

- `dhl-label.exe`: onefile, windowed (keine Konsole), Icon `icon.ico`.
  Ohne Argument → Setup-GUI; `setup`-Unterbefehl dito; `printers`/
  `show-config` zeigen Dialogfenster, wenn stdout fehlt.
- CI (`windows-build.yml`): Tests unter ubuntu (inkl. `bash -n` der
  Shell-Installer – schützt die Mint-Seite) und windows → PyInstaller-Build →
  Artefakt; bei Tag `v*` hängt `softprops/action-gh-release` die EXE ans
  Release an.
- Lokal testen: venv mit `requirements-windows.txt` + `pyinstaller`,
  `python -m PyInstaller dhl-label-win.spec --noconfirm`.
