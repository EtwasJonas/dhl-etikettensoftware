# Status & offene Aufgaben

> Agenten: **Diese Datei zuerst lesen** und nach erledigten Aufgaben aktualisieren
> (inkl. Datum). Letzte Aktualisierung: 2026-11-12.

## Aktueller Stand: Windows 11 am echten Drucker verifiziert + eingerichtet

`origin/main` = git log. Repo **öffentlich**.

### Realer Hardware-Test Windows (03.11.2026, SN 420B/Vretti, USB) ✓

- Zwei echte DHL-Privatkunden-A4-Paketmarken durch die Pipeline → Testdrucke
  auf dem SN 420B (4"x6"-Rollen): **funktioniert**.
- Erkenntnisse/Korrekturen aus dem Echtbetrieb:
  1. Scheren-Linie am A4-Mittelfalz war im Standard-Crop → jetzt per Zuschnitt
     entfernt (`trim_top/bottom/left/right_mm`).
  2. Treiber-Vorgabe „4 x 6" misst 104,23 mm statt 101,6 → Inhalt saß versetzt →
     **Custom-Size** (`DMPAPER_USER` + PaperWidth/Length = exakt
     `target_size_mm`) statt Treiber-Papier, wenn Zielgröße gesetzt.
  3. 1:1-Rendering wirkte „zu dünn" → jetzt **4× Übersampling + BOX-Downsampling
     + Schwellwert 170** (Schwarz/Weiß) → volle Striche.
  4. Zentrierung auf der physischen Seite; 1:1-Zeichnung am Seitenursprung,
     wenn Bild == Seite (Druck == PDF-Geometrie).
- Finale Kalibrier-Werte (docs/architektur.md §9.3): `trim_top 16.24 /
  trim_bottom 16.66 / trim_left 3.08 / trim_right 4.13`,
  `target 101.6x152.4`, `rotate auto`. Druckidentisch gemessen: Rand
  oben 5,00 / unten 5,13 mm, links/rechts je 13,39 mm, Inhalt 74,9×142,4 mm,
  Schere weg, Barcode/QR unverzerrt.
- Nutzer-PC fertig eingerichtet: Config in `%APPDATA%\dhl-label\config.conf`,
  EXE in `%LOCALAPPDATA%\DHL-Etiketten\dhl-label.exe`, Autostart-Verknüpfung
  → installierte EXE, Watcher läuft (Downloads-Ordner, Filter
  `versand|dhl|paket`).
- Windows-GUI: EXE wird beim „Einrichten" nach `%LOCALAPPDATA%\DHL-Etiketten`
  installiert (Autostart zeigt auf die Installation, nicht auf Downloads);
  Zuschnitt-Felder oben/unten/links/rechts.

### Mint/Linux (unverändert geblieben)

- GTK-Setup-GUI, install.sh, systemd-Dienst – Funktionsweise unverändert;
  neue Config-Schlüssel (`trim_left/right_mm`) sind optionale Defaults (0.0).
- tests/test_core.py: 16 Tests (inkl. x-Zuschnitt-Region), CI grün auf
  Linux + Windows.

### Linux-Parität „Option A“ umgesetzt (03.11.2026)

- **Zuschnitt-Felder (mm oben/unten/links/rechts) in der GTK-GUI:**
  im Hauptformular (Vorbefüllung aus der installierten Config, Validierung)
  und im **Kalibrier-Dialog** mit **„Werte speichern“** – schreibt die
  config.conf via `gh.write_config_file` + `systemctl --user restart
  dhl-label`, damit Feintuning während der Kalibrierung OHNE Installer-Lauf
  (apt/pkexec/venv) möglich ist. Alle Varianten nutzen die Dialog-Werte als
  Basis (`--trim-*` vor den Varianten-Args); Variante 2/3 überschreiben
  oben/unten mit 5 mm.
- **install.sh:** neue Flags `--trim-top/--trim-bottom/--trim-left/
  --trim-right` (Komma→Punkt + Zahlen-Regex, Validierung BEVOR installiert
  wird), interaktive Fragen (4 Prompts mit Erklärtext, Enter = 0),
  config.conf schreibt jetzt alle vier Keys (zuvor fehlten left/right ganz).
- **gui_helpers:** `parse_trim_mm` (Komma erlaubt, ≥ 0, NaN/inf abgelehnt),
  `build_install_cmd` mit Trim-Params, `write_config_file` mit neuem
  `extra_options`-Param (manuelle lp-Optionen bleiben beim GUI-Speichern
  erhalten). Windows-GUI nutzt denselben Parser (einheitliche Validierung).
- **dhl_label:** `show-config` zeigt auch trim_left/right; `calibrate`-Hints
  nennen alle vier Keys.
- tests/test_core.py: **18 Tests** (+`parse_trim_mm`, +`build_install_cmd`
  mit Trims), lokal grün; Smoketest Windows-GUI (Vorbefüllung + save-Pfad)
  grün. GTK-GUI nur py_compile + Lesen (unter Windows nicht lauffähig).

### Werks-Kalibrierung ausgeliefert (12.11.2026)

- Neue **`defaults.conf`** mit den verifizierten Werten (SN 420B, 03.11.):
  `side = top`, `trim_top_mm = 16.24`, `trim_bottom_mm = 16.66`,
  `trim_left_mm = 3.08`, `trim_right_mm = 4.13`,
  `target_size_mm = 101.6x152.4`, `rotate = auto` – inkl. Herkunfts-Doku.
- **Alle Setups lesen sie als Vorbefüllung** (`gh.load_defaults()`, nie-wirft):
  Windows-GUI (tkinter), GTK-GUI (Etikettengröße + alle vier Trims),
  install.sh (füllt nicht gesetzte `--trim-*`-Flags; interaktive
  Etikettengröße schlägt den Default vor). EXE bündelt die Datei (`_MEIPASS`,
  Spec-Datas), install.sh kopiert sie nach APP_DIR.
- Wirkung: Neu-Nutzer wählen nur Drucker + Papierformat → **exakt das
  verifizierte Druckergebnis** (Rand oben/unten 5 mm, seitlich 13,4 mm,
  Schere draußen, Uniform-Scale). Bestehende config.conf bleiben unangetastet
  (Config-Fallbacks bleiben neutral 0.0/leer).
- tests/test_core.py: **20 Tests** (+`load_defaults`-Inhalt, +BOM/LF-Check
  für defaults.conf), lokal grün.

## Nächster Schritt / offene Punkte (Einstieg für die neue Sitzung)

- **Release v1.1.0 ist live** (03.11.2026): `dhl-label.exe` hängt am Release
  (https://github.com/EtwasJonas/dhl-etikettensoftware/releases), gebaut von CI
  aus `b3d30f0`. Hinweis: Workflow-Berechtigung `contents: write` nachgereicht
  (`cc09cc0`) – bei zukünftigen Tags `v*` baut + hängt CI die EXE automatisch an.
  → **Neue Version mit defaults.conf als `v1.2.0` releasen** (siehe oben).
- **Offene Entscheidung (Nutzer):** Linux-Qualität angleichen (**Option B**)?
  Eigene Rasterung auf Linux (pypdfium2/Pillow als neue Linux-Deps, gerastertes
  Schwarz/Weiß-PDF via lp) – erst nach dem ersten echten Mint-Test entscheiden,
  ob CUPS nicht ohnehin gut genug druckt. **Option A (trims auf Linux) ist
  erledigt** (siehe oben) und bekommt die Werks-Werte jetzt automatisch.
- **Alltagsbetrieb Windows läuft** (Watcher auf dem Nutzer-PC aktiv,
  EXE installiert unter `%LOCALAPPDATA%\DHL-Etiketten\`).
- **Mint-PC:** erster echter Test + Endkalibrierung vor Ort – die Werks-Kalibrierung
  wird dort als Vorbefüllung mitgeliefert, aber das Druckergebnis durch CUPS
  (Media/Ränder) muss einmal geprüft/feinjustiert werden.
  Lokale Test-Artefakte für die Vermessung: `testdrucke/` (gitignored,
  Windows-lastig – Vermessungs-Skripte mit numpy/pypdfium2).

## Bekannte Restrisiken

1. DHL-Layout-Änderungen (Marke verschiebt sich im A4) → Zuschnitt-Werte
   neu kalibrieren (GUI-Felder) – langfristig: automatische Marker-Erkennung.
2. Andere Treiber/Papier-Definitionen: Custom-Size deckt Zielgrößen ab;
   ohne `target_size_mm` greift das Papier-Namensmatch.
3. pkexec-Passwortdialog im GUI-Kontext (polkit) – falls er nicht erscheint,
   Terminal-Fallback `bash install.sh` dokumentiert.
4. Windows: SmartScreen-Warnung beim ersten Start der EXE („Trotzdem
   ausführen") – dokumentiert im README.

## Aktive Codetasks: keine

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
- `28a70be`/`2990955` Windows-Support: win_backend.py (GDI-Druck, Autostart, Lock),
  setup_gui_win.py (tkinter), tests/test_core.py, CI-Workflow + PyInstaller-EXE
- 03.11.2026: trim_left/right_mm, Custom-Size exakt nach target_size_mm,
  4×-Übersampling+Schwellwert-Rasterung, 1:1-Zeichnung, EXE-Installation in
  %LOCALAPPDATA%\DHL-Etiketten, realer Hardware-Test SN 420B bestanden
- 03.11.2026: Option A – Zuschnitt-Felder in GTK-GUI (Formular + Kalibrier-
  Dialog mit „Werte speichern“), install.sh-Flags --trim-*/Fragen/Config-Keys,
  parse_trim_mm, write_config_file(extra_options), 18 Tests
