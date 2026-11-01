# Architektur & Technische Details

## 1. Datei-Zuständigkeiten

| Datei | Rolle |
|---|---|
| `dhl_label.py` | Kern-CLI: `watch` `print` `print-latest` `crop` `calibrate` `show-config` `printers` `print-pdf`. Crop/Dreh/Skalier-Logik (pypdf), lp-Druck, Watcher-Loop. **Kein** GUI-Code. |
| `gui_helpers.py` | Pure Logik ohne GTK (Windows-testbar): `list_printers`, `media_sizes`, `parse_size_mm`, `build_install_cmd`, `calibration_variants`, `build_crop_cmd`, `build_print_cmd`, `check_environment`, `read_installed_config`, `installed_state` (Erkennung bestehender Installation für die GUI). |
| `icon.png` | Fenster-/Desktop-Icon der GUI und der Desktop-Einträge. |
| `setup_gui.py` | GTK3-Setup-Assistent (Formular → install.sh-Flags → Log-Streaming → Erfolg → GUI-Kalibrierdialog; Installations-Erkennung mit Vorbefüllung, Deinstallieren-Knopf). Läuft mit **System-Python** (`/usr/bin/python3`), nicht im venv (GTK liegt im System, pypdf im venv). |
| `setup-gui.sh` | Doppelklick-Launcher für die GUI (`exec /usr/bin/python3 "$(dirname "$0")/setup_gui.py"`); braucht einmalig exec-Bit nach ZIP-Entpacken. |
| `install.sh` | Installer, zwei Modi: interaktiv (kein Argument, Terminal-Fallback) und nicht-interaktiv per Flags (GUI ruft auf): `--printer --media --target --watch-mode downloads|custom --watch-dir --pattern --side top|bottom --no-calibrate --pkexec --non-interactive`. Im Nicht-interaktiv-Modus Pflicht-Flags validieren (sonst würde read hängen). |
| `uninstall.sh` | Entfernt Service, Dateien, Icons, Config. Wird von install.sh zusätzlich nach APP_DIR kopiert (GUI kann aus installierter Kopie deinstallieren). |
| `dhl-label.service` | systemd-User-Unit, `ExecStart=%h/.local/bin/dhl-label watch`, `Restart=on-failure`, `WantedBy=default.target`. |
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
  Watch-Modus/Side), mit Einsteiger-Erklärtexten.
- Mit Flags: `--pkexec` für apt (GUI-Passwortdialog), `--non-interactive`
  verhindert JEDES `read` (Pflicht-Flags werden vorher validiert, sonst `die`).
  `--target ""` (leer) ist erlaubt = nur croppen; in `--non-interactive` darf der
  leere Wert NICHT zum interaktiven Prompt führen (Bedingung: `-n FLAG_TARGET || NONINTERACTIVE`).

## 6. Windows-Test-Werkzeuge (Entwickler-PC)

- pypdf in `$env:TEMP\opencode\pylibs` (PYTHONPATH setzen).
- Test-A4: `PdfWriter(); add_blank_page(width=595.28, height=841.89)`; PDF **mit Inhalt**:
  blank page + `page.replace_contents(DecodedStreamObject mit set_data(b"...re f"))`.
- BOM-freies Schreiben von Testscripts: `[IO.File]::WriteAllText(path, text, [System.Text.UTF8Encoding]::new($false))`.
- Config für Tests: `$env:DHL_LABEL_CONFIG` → Temp-Pfad, BOM-frei!
- Bash: `C:\Program Files\Git\bin\bash.exe` (`-n` Syntaxcheck, `install.sh --help` testbar ohne apt).
- lp/gs existieren nicht unter Windows → `print_pdf` gibt False (getesteter Fehlerpfad), Watcher-Test mit druckfehlern prüft Retry-Logik.

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
