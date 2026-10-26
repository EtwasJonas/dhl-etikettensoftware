# DHL Etikettensoftware

Croppt die DHL-Versandmarke aus dem A4-PDF des DHL-Privatkundenportals
(Marke in der oberen Seitenhälfte) und druckt sie automatisch auf einen
Thermoetikettendrucker (z.B. Vretti 4x6, per USB/CUPS) – **ohne Druckdialog**.

## Installation (Ein-Klick auf dem Ziel-PC, Ubuntu/Debian/Mint)

```bash
./install.sh
```

Der Installer fragt interaktiv ab:
- Drucker (via `lpstat`) und Mediengröße (via `lpoptions`)
- Watch-Modus: **Downloads-Ordner mit Namensfilter** (`versand|dhl`)
  oder **eigener Watch-Ordner** (alle PDFs)
- Position der Marke im A4-PDF (obere/untere Hälfte)
- Ob direkt ein Kalibrierungsdruck gestartet werden soll

Danach läuft ein systemd-User-Service (`dhl-label.service`), der den
Watch-Ordner überwacht. Ein Desktop-Icon „DHL-Marke drucken" dient als
manuelle Fallback-Auslösung (druckt die neueste passende PDF).

## Ablauf im Alltag

1. Im DHL-Portal PDF erzeugen und herunterladen (landet im Watch-Ordner)
2. Sekunden später druckt der Vretti nur die Versandmarke
3. Die verarbeitete PDF wandert nach `<Watch-Ordner>/gedruckt/`
   (verhindert Doppeldruck). Schlägt der Druck 3-mal fehl (z.B. Drucker
   offline), landet die PDF in `<Watch-Ordner>/fehlgeschlagen/` und kann
   manuell nachgedruckt werden: `dhl-label print DATEI.pdf`

## Befehle

```bash
dhl-label watch              # Watcher manuell starten (sonst macht das systemd)
dhl-label print DATEI.pdf    # Bestimmte PDF drucken
dhl-label print-latest       # Neueste passende PDF drucken (Desktop-Icon)
dhl-label crop IN [OUT]      # Nur croppen, als Vorschau-PDF speichern
dhl-label calibrate [PDF]    # Kalibrierungsdrucke erzeugen
dhl-label show-config        # Effektive Konfiguration anzeigen
```

## Kalibrierung

`dhl-label calibrate` druckt nacheinander 4 Testvarianten (mit Bestätigung
per Enter, jede Etikette beschriften):

1. Obere Hälfte exakt (pypdf)
2. 5 mm oben abgeschnitten (`trim_top_mm = 5.0`)
3. 5 mm unten abgeschnitten (`trim_bottom_mm = 5.0`)
4. Ghostscript-Hardcrop (Fallback, falls pypdf-Ergebnis verschoben ist)

Passt keine Variante: Werte in `~/.config/dhl-label/config.conf` unter
`[crop]` anpassen (auch `trim_top_mm`/`trim_bottom_mm` in 1-mm-Schritten)
und mit `dhl-label crop DATEI.pdf` eine Vorschau ohne Druck erzeugen.

## Konfiguration

`~/.config/dhl-label/config.conf`:

```ini
[printer]
name = Vretti                 # lpstat -p
media = 4x6                   # lpoptions -p Vretti -l
extra_options =               # zusaetzliche lp-Optionen, z.B. "-o landscape"

[crop]
side = top                    # top | bottom | full
trim_top_mm = 0.0
trim_bottom_mm = 0.0
page_index = 0                # 0 = erste Seite
use_ghostscript = false       # Fallback-Cropping

[watch]
mode = downloads              # downloads (mit Namensfilter) | custom (alle PDFs)
dir = /home/USER/Downloads
filename_pattern = versand|dhl|paket 
processed_dirname = gedruckt
poll_seconds = 2.0
process_existing = false
```

## Fehlersuche

```bash
journalctl --user -u dhl-label -f     # Live-Log des Watchers
systemctl --user restart dhl-label    # Watcher neu starten
lpstat -p                             # Drucker erreichbar?
lp -d Vretti -o media=4x6 test.pdf    # Druckpfad direkt testen
```

## Deinstallation

```bash
./uninstall.sh
```

## Dauerlösung-Hinweis

Das DHL-Geschäftskundenportal kann Versandmarken direkt als 10x15-cm-PDF
(ohne A4-Zusatzlayout) ausgeben – langfristig die sauberere Lösung, falls
du ohnehin Geschäftskunden-Zugang hast.
