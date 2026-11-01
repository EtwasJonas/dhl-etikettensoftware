# DHL Etikettensoftware

Croppt die DHL-Versandmarke aus dem A4-PDF des DHL-Privatkundenportals
und druckt sie automatisch auf einen Thermoetikettendrucker (z.B. Vretti
4x6, per USB oder WLAN) – **ohne Druckdialog**. Läuft auf Linux Mint
(CUPS) und Windows 11 (Windows-Druckertreiber).

Einmal eingerichtet läuft ein Hintergrunddienst: DHL-PDF herunterladen →
wenige Sekunden später kommt die Versandmarke aus dem Drucker.

## Windows 11: Installation per EXE (kein Python nötig)

Für Windows gibt es eine fertige EXE, die automatisch bei jedem Update
des Projekts neu gebaut wird:

**Schritt 1 – EXE herunterladen:** auf der GitHub-Seite unter
**Releases** die neueste Version öffnen und `dhl-label.exe`
herunterladen (Quelle: GitHub Actions Build dieser EXE):

```
https://github.com/EtwasJonas/dhl-etikettensoftware/releases
```

**Schritt 2 – Doppelklick auf `dhl-label.exe`** → das Setup-Fenster
öffnet sich (keine Konsole, kein Python nötig):

1. **Drucker** aus der Liste wählen (USB-Drucker richtet Windows
   automatisch ein; „Neu laden“ aktualisiert die Liste)
2. **Papierformat** übernehmen (das meldet der Windows-Druckertreiber,
   z.B. „User Defined 100x150mm“)
3. **Etikettengröße der Rolle** eintragen (meist `100x150` mm)
4. **Wann gedruckt** wird: Downloads-Ordner mit Namensfilter
   (`versand|dhl|paket`) oder eigener Watch-Ordner
5. Position der Marke im A4-PDF (obere/untere Hälfte)
6. **„Einrichten“** – es gibt keine Admin-Abfrage; die Einstellungen
   liegen danach unter `%APPDATA%\dhl-label\config.conf` und die
   Autostart-Verknüpfung im Startmenü-Autostart-Ordner

**Schritt 3 – Kalibrieren (optional, empfohlen):** Nach dem Einrichten
erscheint der Kalibrier-Dialog: Variante wählen, **jeder Testdruck
passiert nur nach Bestätigung**, Etikette beschriften und vergleichen.
Passt eine Variante, die Werte im Setup-Fenster anpassen (Zuschnitt-mm,
Etikettengröße) und erneut „Einstellungen aktualisieren“ klicken.
Hinweis: Variante 4 (Ghostscript) gibt es nur unter Linux.

Danach läuft der **Watcher** im Hintergrund (startet ab jetzt bei jeder
Anmeldung selbst). Doppelklick auf die EXE öffnet jederzeit wieder das
Setup-/Einstellungs-Fenster.

**Hinweise:**

- Log-Datei: `%LOCALAPPDATA%\dhl-label\dhl-label.log` (die EXE hat keine
  Konsole – alles landet dort, inkl. Druckfehler)
- `dhl-label.exe printers` zeigt die Druckerliste in einem Fenster
  (statt Konsole), `show-config` ebenfalls
- Deinstallieren: EXE öffnen → **„Deinstallieren…“** – entfernt Watcher,
  Autostart und Einstellungen; PDFs bleiben erhalten
- Windows Defender SmartScreen kann beim ersten Start nachfragen
  („Weitere Informationen“ → „Trotzdem ausführen“) – die EXE wird von
  GitHub Actions direkt aus diesem Repository gebaut

## Installation mit der GUI (Linux Mint – kein Terminal nötig)

Die GUI (GTK-Fenster) ist auf Linux Mint/Ubuntu sofort lauffähig, weil
PyGObject dort vorinstalliert ist.

**Schritt 1 – Herunterladen** (im Browser, eingeloggt bei GitHub):

```
https://github.com/EtwasJonas/dhl-etikettensoftware/archive/refs/heads/main.zip
```

**Schritt 2 – Entpacken** (Rechtsklick auf die ZIP → „Hier entpacken“)

**Schritt 3 – Einmalig ausführbar machen:** Ein ZIP verliert die
Information „diese Datei ist ein Programm“. Rechtsklick auf
**`setup-gui.sh`** → **Eigenschaften** → **Berechtigungen** →
**„Ausführen erlauben“** (Haken setzen). Danach startet ein Doppelklick
die GUI direkt – kein Terminal.

**Schritt 4 – Einrichten im Fenster:**
1. **Drucker** aus der Liste wählen (USB und WLAN werden gleich
   angezeigt; „Neu laden“ aktualisiert, wenn das Gerät erst jetzt
   verbunden wurde)
2. **Mediengröße** übernehmen (vorausgewählt ist, was der Drucker
   meldet – meist `4x6`)
3. **Etikettengröße der Rolle** eintragen (Vretti-Rollen meist `100x150` mm)
4. Wählen, **wann gedruckt** wird: Downloads-Ordner mit Namensfilter
   (`versand|dhl|paket`) oder eigener Watch-Ordner (alle PDFs)
5. Wo die Marke im A4-PDF sitzt: **obere/untere Hälfte**
6. **„Installation starten“** – ein Passwortdialog (pkexec) erscheint
   für die Systempakete; der Fortschritt läuft live im Fenster mit

**Schritt 5 – Kalibrieren (optional, empfohlen):** Nach der Installation
erscheint „Jetzt kalibrieren (Testdrucke)“. Variante wählen, jede
Ausgabe auf dem Etikett mit einer Nummer beschriften und vergleichen –
**jeder Testdruck passiert nur nach Bestätigung**. Passt eine Variante,
nochmal dieselbe Zahl in `~/.config/dhl-label/config.conf` unter `[crop]`
eintragen (oder das Setup erneut laufen lassen und die Werte dort setzen).

Danach schließt das Fenster – im Hintergrund läuft der Watcher als
systemd-User-Service und startet bei jeder Anmeldung selbst.

> **Wenn der Doppelklick nicht klappt** (Dateimanager öffnet die Datei im
> Editor statt sie auszuführen): im entpackten Ordner ein Terminal öffnen
> und `bash install.sh` starten – der Installer fragt alles interaktiv ab
> (gleiche Fragen wie die GUI, nur textbasiert). Alternativ:
> `python3 setup_gui.py` startet die GUI aus dem Terminal heraus.

## Installation im Terminal (Fallback)

```bash
bash install.sh
```

(`bash install.sh` statt `./install.sh` – dann braucht man keine
Ausführungsrechte zu setzen.)

Der Installer fragt interaktiv ab:
- Drucker (via `lpstat`) – USB und WLAN gleichberechtigt
- **Mediengröße** (via `lpoptions`): interner CUPS-Name der Etiketten-/Papiergröße
  (z.B. `4x6`); der Vorschlag ist bereits das, was der Drucker meldet –
  einfach mit Enter übernehmen
- **Etikettengröße der Rolle** (z.B. `100x150`): das gecroppte A4-Stück wird
  auf diese Größe gedreht und exakt eingepasst
- Watch-Modus: **Downloads-Ordner mit Namensfilter** (`versand|dhl|paket`)
  oder **eigener Watch-Ordner** (alle PDFs)
- Position der Marke im A4-PDF (obere/untere Hälfte)
- Ob direkt ein Kalibrierungsdruck gestartet werden soll

## Ablauf im Alltag

1. Im DHL-Portal PDF erzeugen und herunterladen (landet im Watch-Ordner)
2. Sekunden später druckt der Vretti nur die Versandmarke
3. Die verarbeitete PDF wandert nach `<Watch-Ordner>/gedruckt/`
   (verhindert Doppeldruck). Schlägt der Druck 3-mal fehl (z.B. Drucker
   offline), landet die PDF in `<Watch-Ordner>/fehlgeschlagen/` und kann
   manuell nachgedruckt werden: `dhl-label print DATEI.pdf`

## Befehle

Linux (Wrapper `dhl-label`, vom Installer eingerichtet):

```bash
dhl-label watch              # Watcher manuell starten (sonst macht das systemd)
dhl-label print DATEI.pdf    # Bestimmte PDF drucken
dhl-label print-latest       # Neueste passende PDF drucken (Desktop-Icon)
dhl-label crop IN [OUT]      # Nur croppen/einpassen, als Vorschau-PDF speichern
dhl-label calibrate [PDF]    # Kalibrierungsdrucke erzeugen (jede mit Bestätigung)
dhl-label print-pdf DATEI.pdf # Fertig aufbereitete PDF direkt drucken (ohne Crop)
dhl-label show-config        # Effektive Konfiguration anzeigen
dhl-label printers           # Drucker (USB/WLAN) mit Verbindungsart auflisten
```

Windows (`dhl-label.exe`, windowed-EXE ohne Konsole):

```
dhl-label.exe                # Setup-/Einstellungs-Fenster öffnen
dhl-label.exe setup          # dito
dhl-label.exe watch          # Watcher (macht normalerweise die Autostart-Verknüpfung)
dhl-label.exe print DATEI.pdf
dhl-label.exe print-latest
dhl-label.exe crop IN [OUT]
dhl-label.exe calibrate [PDF]
dhl-label.exe print-pdf DATEI.pdf
dhl-label.exe show-config    # Ausgabe auch als Dialogfenster
dhl-label.exe printers       # Druckerliste als Dialogfenster
```

Ausgaben der EXE landen (weil sie kein Konsolenfenster hat) in
`%LOCALAPPDATA%\dhl-label\dhl-label.log`.

Erneut einrichten (z.B. anderer Drucker): Desktop-Icon **„DHL-Setup“**
oder `dhl-label-setup` im Terminal – die GUI zeigt dann
**„✓ Bereits installiert“** mit den aktuellen Werten und den Knopf
**„Einstellungen aktualisieren“** (vorausgewählt sind Drucker, Medium,
Ordner usw.). Nach dem Klick übernimmt der Hintergrunddienst die neuen
Einstellungen sofort – es wird nichts neu heruntergeladen. Beide
Desktop-Verknüpfungen („DHL-Setup“ und „DHL-Marke drucken“) nutzen das
DHL-Icon.

## Druckerwahl (USB oder WLAN)

Der Installer listet bei der Einrichtung **alle** in CUPS eingerichteten
Drucker auf – unabhängig davon, ob sie per USB oder WLAN/Netzwerk
verbunden sind (`lpstat -p` inkl. Status, z.B. „idle“ oder „disabled“).
Der gewählte Druckername wird in der Konfiguration gespeichert; der
Druck selbst läuft über `lp -d <Name>` und CUPS kümmert sich um den
Transport. Ein WLAN-Drucker verhält sich also exakt wie ein USB-Drucker.

Später prüfen: `dhl-label printers` zeigt jeden Drucker samt Geräte-URI
(`usb://…` = USB, `ipp://…`/`socket://…`/`dnssd://…` = WLAN/Netzwerk).
Ändern: Druckername in `~/.config/dhl-label/config.conf` unter `[printer]`
tauschen, danach `systemctl --user restart dhl-label`.

## Kalibrierung

Es werden nacheinander bis zu 6 Testvarianten vorgeschlagen – **jeder
Testdruck passiert nur nach deiner Bestätigung** (GUI-Dialog bzw. Enter
im Terminal). Die Etikette danach beschriften, um die Variante zu
identifizieren:

1. Obere Hälfte exakt (pypdf)
2. 5 mm oben abgeschnitten (`trim_top_mm = 5.0`)
3. 5 mm unten abgeschnitten (`trim_bottom_mm = 5.0`)
4. Ghostscript-Hardcrop (Fallback, falls pypdf-Ergebnis verschoben ist)
5. Gedreht + exakt auf **100x150 mm** eingepasst
6. Gedreht + exakt auf **101,6x152,4 mm** (4"×6") eingepasst

**Warum Variante 5/6?** Die halbe A4-Seite (210 × 148,5 mm) hat ein
anderes Seitenverhältnis als ein 4x6-Etikett (100 × 150 mm). Mit
`target_size_mm` wird der Markenbereich daher automatisch gedreht und
proportional auf die Etikettengröße eingepasst – der Drucker bekommt ein
PDF in exakter Etikettengröße und druckt randnah. Die Skalierung ist
stets gleichmäßig (keine Verzerrung), damit Barcode/QR-Code scannbar
bleiben.

Passt keine Variante: Werte in `~/.config/dhl-label/config.conf` unter
`[crop]` anpassen und mit `dhl-label crop DATEI.pdf` eine Vorschau-PDF
ohne Druck erzeugen (öffnet sie z.B. mit einem PDF-Viewer zum Prüfen):

- `trim_top_mm` / `trim_bottom_mm` – Markenbereich eingrenzen (mm)
- `target_size_mm` – z.B. `100x150`; leer = nur croppen
- `rotate` – `auto` (Standard), `0`, `90`, `270` (falls die Marke
  verkehrt herum auf dem Etikett landet)

## Konfiguration

Linux: `~/.config/dhl-label/config.conf` – Windows:
`%APPDATA%\dhl-label\config.conf` (gleiche Struktur):

```ini
[printer]
name = Vretti                 # Linux: lpstat -p | Windows: Name in "Drucker & Scanner"
media = 4x6                   # Linux: lpoptions -p Vretti -l | Windows: Papierformat des Treibers
extra_options =               # zusaetzliche lp-Optionen (nur Linux, z.B. "-o landscape")

[crop]
side = top                    # top | bottom | full
trim_top_mm = 0.0
trim_bottom_mm = 0.0
page_index = 0                # 0 = erste Seite
use_ghostscript = false       # Fallback-Cropping (nur Linux – gs gibt es unter Windows nicht)
target_size_mm = 100x150      # exakte Etikettengroesse; leer = nur croppen
rotate = auto                 # auto | 0 | 90 | 270

[watch]
mode = downloads              # downloads (mit Namensfilter) | custom (alle PDFs)
dir = /home/USER/Downloads    # Windows z.B. C:\Users\NAME\Downloads
filename_pattern = versand|dhl|paket 
processed_dirname = gedruckt
poll_seconds = 2.0
process_existing = false
```

## Fehlersuche

Linux:

```bash
journalctl --user -u dhl-label -f     # Live-Log des Watchers
systemctl --user restart dhl-label    # Watcher neu starten
lpstat -p                             # Drucker erreichbar?
lp -d Vretti -o media=4x6 test.pdf    # Druckpfad direkt testen
```

Windows:

```
%LOCALAPPDATA%\dhl-label\dhl-label.log   # Live-Log (mit Editor öffnen)
dhl-label.exe printers                   # Druckerliste + Papierformate
```

- Watcher läuft doppelt? Der Watcher schützt sich selbst (zweiter Start
  beendet sich, Lock: `%LOCALAPPDATA%\dhl-label\watcher.lock`).
- Drucker fehlt in der Liste: USB-Kabel anstecken/Drucker einschalten,
  dann im Setup „Neu laden“.
- Marke verkehrt herum: in der config.conf `[crop] rotate = 270` setzen
  (oder Setup erneut ausführen – dort Kalibrierung nutzen).

GUI startet nicht: `dhl-label-setup` im Terminal ausführen und die
Meldung lesen (meist fehlt `python3-gi`: `sudo apt install python3-gi`).
Windows: EXE neu herunterladen, Log-Datei prüfen.

## Deinstallation

**Linux per GUI (empfohlen):** „DHL-Setup“ öffnen → roter Knopf
**„Deinstallieren…“** → Bestätigen. Es werden der Hintergrunddienst
(Watcher), das Programm, die Einstellungen und die Desktop-Verknüpfungen
entfernt; deine PDFs im Watch-Ordner bleiben erhalten.

**Linux im Terminal:**

```bash
./uninstall.sh
```

**Windows:** `dhl-label.exe` öffnen → **„Deinstallieren…“** → Bestätigen.
Es werden der Watcher beendet, die Autostart-Verknüpfung und die
Einstellungen (`%APPDATA%\dhl-label\config.conf`) entfernt; deine PDFs
im Watch-Ordner bleiben erhalten. Die EXE selbst kann einfach gelöscht
werden.

## Dauerlösung-Hinweis

Das DHL-Geschäftskundenportal kann Versandmarken direkt als 10x15-cm-PDF
(ohne A4-Zusatzlayout) ausgeben – langfristig die sauberere Lösung, falls
du ohnehin Geschäftskunden-Zugang hast.
