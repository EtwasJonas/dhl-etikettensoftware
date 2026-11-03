# Status & offene Aufgaben

> Agenten: **Diese Datei zuerst lesen** und nach erledigten Aufgaben aktualisieren
> (inkl. Datum). Letzte Aktualisierung: 2026-11-03.

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

## Nächster Schritt / offene Punkte (Einstieg für die neue Sitzung)

- **Release v1.1.0 ist live** (03.11.2026): `dhl-label.exe` hängt am Release
  (https://github.com/EtwasJonas/dhl-etikettensoftware/releases), gebaut von CI
  aus `b3d30f0`. Hinweis: Workflow-Berechtigung `contents: write` nachgereicht
  (`cc09cc0`) – bei zukünftigen Tags `v*` baut + hängt CI die EXE automatisch an.
- **Offene Entscheidung (Nutzer):** Linux angleichen?
  - **Option A (klein):** Zuschnitt-Felder (oben/unten/links/rechts) in GTK-GUI +
    install.sh + Kalibriervarianten; trims funktionieren auf Linux bereits
    (Core-Code + Config-Keys, CLI-Flags vorhanden) – nur die Linux-Tools
    fragen sie noch nicht ab.
  - **Option B (mittel):** eigene Rasterung auf Linux (pypdfium2/Pillow als neue
    Linux-Deps, gerastertes Schwarz/Weiß-PDF via lp) – erst nach dem ersten
    echten Mint-Test entscheiden, ob CUPS nicht ohnehin gut genug druckt.
- **Alltagsbetrieb Windows läuft** (Watcher auf dem Nutzer-PC aktiv,
  EXE installiert unter `%LOCALAPPDATA%\DHL-Etiketten\`).
- **Mint-PC:** erster echter Test + Endkalibrierung vor Ort – die Windows-
  Kalibrier-Werte gelten NICHT automatisch (CUPS-Media/Ränder können abweichen).
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
