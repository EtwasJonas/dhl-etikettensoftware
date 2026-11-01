# Status & offene Aufgaben

> Agenten: **Diese Datei zuerst lesen** und nach erledigten Aufgaben aktualisieren
> (inkl. Datum). Letzte Aktualisierung: 2026-11-01.

## Aktueller Stand: Code komplett, Wartet auf echten Test auf dem Mint-PC

`origin/main` = `429545c` (lokal und GitHub synchron, Repo **öffentlich** – Nutzer-
Entscheidung vom 01.11.2026). Der GUI-Setup-
Assistent ist fertig implementiert und Windows-seitig getestet:

- `setup_gui.py`: GTK3-Formular → install.sh (nicht-interaktiv, pkexec-Passwortdialog)
  → Log-Streaming → Erfolgsmeldung → GUI-Kalibrierdialog (6 Varianten, Bestätigungsdialog
  vor jedem Testdruck)
- Installations-Erkennung: Banner „Bereits installiert", Formular-Vorbefüllung,
  Knopf wird zu „Einstellungen aktualisieren" (erneutes Einrichten übernimmt frische
  config.conf, systemd-Dienst wird dabei neu gestartet – Commit `476e0e3`)
- Deinstallieren-Knopf (Bestätigungsdialog, streamt uninstall.sh-Ausgabe)
- `setup-gui.sh`: Doppelklick-Launcher (System-Python, exec-Bit-Hinweis als Kommentar)
- `icon.png`: Fenster-/Desktop-Icon
- Windows-Tests grün: py_compile aller Python-Dateien, bash -n, GUI-Logik-Tests

## Nächster Schritt: Erste echte Installation auf dem Ziel-PC (Linux Mint)

**Vom Nutzer auszuführen, Agent begleitet interaktiv:**

1. ZIP laden: `https://github.com/EtwasJonas/dhl-etikettensoftware/archive/refs/heads/main.zip`
   → entpacken → exec-Bit für `setup-gui.sh` setzen (Rechtsklick → Eigenschaften →
   Berechtigungen → „Ausführen erlauben") → Doppelklick → „Ausführen"
2. Setup-GUI durchlaufen (Vretti muss verbunden sein: USB **oder** WLAN)
3. Kalibrierung mit einer echten heruntergeladenen DHL-PDF (6 Varianten testen)
4. Alltags-Check: nächste DHL-PDF downloaden → Marke druckt automatisch, verarbeitete
   PDF landet in `gedruckt/`

### Offene Punkte, die dabei vom Nutzer zu klären sind (docs/projekt.md §Offene Punkte)

- `lpstat -p` und `lpoptions -p <DRUCKER> -l | grep -i size` Ausgaben (bei Problemen
  den Agenten schicken)
- Kalibrier-Ergebnis: welche Variante passt, nötige `trim_top_mm`/`trim_bottom_mm`
- Namensfilter `versand|dhl|paket` vs. realer Dateiname der DHL-PDF
- Falls Marke auf dem Kopf gedruckt wird: `rotate = 270` in der Config setzen

## Bekannte Restrisiken (nur auf Mint-PC klärbar)

1. CUPS-Medianame des Vretti (GUI liest ihn vor, Nutzer bestätigt).
2. Passt der Crop exakt (Kalibrierung entscheidet).
3. pkexec-Passwortdialog im GUI-Kontext (polkit) – falls er nicht erscheint,
   Terminal-Fallback `bash install.sh` dokumentiert.

## Aktive Codetasks: keine

Sobald der Mint-Test Feedback liefert (z.B. Kalibriernummer, Fehlermeldungen,
`journalctl --user -u dhl-label` Logs), gezielt fixen und als neuen Commit pushen.
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
