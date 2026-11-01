# Projekt & Anforderungen

## Ursprung / Ausgangssituation

Der Nutzer druckt Versandmarken über das **DHL-Privatkundenportal**. Das Portal
erzeugt A4-PDFs mit zweigeteiltem Layout: **Marke in der oberen Hälfte**, unten
Zusatzinfo. Der Drucker ist ein **Vretti 4x6 Thermoetikettendrucker** (Rollen
synonym „100x150 mm“ oder „4"×6“ = 101,6×152,4 mm). Ziel-PC: **Linux Mint**.
Früher: manuelles PDF → Druckdialog mit falschen Einstellungen. Ziel:
„PDF herunterladen → druckt automatisch nur die Versandmarke auf dem Etikett“.

## Nutzer-Präferenzen (zwingend!)

- **Kein Terminal-Betrieb.** Setup als GUI-Fenster, das sich nach erfolgreichem
  Abschluss selbst schließen lässt. Terminal nur als Fallback/Dokumentation.
- **Einsteigerfreundlich**: jede Setup-Frage mit kurzer, verständlicher Erklärung
  (z.B. was „Mediengröße“ überhaupt ist). Defaults so setzen, dass „Enter reichen“.
- **Testdrucke nur nach expliziter Bestätigung** (kein ungewollter Etikettenverbrauch).
- Druck-freie Vorschau (`crop`-Befehl / GUI-Vorschau) ist gewollt und gut.
- Alles auf **Deutsch**.
- Repo auf GitHub **privat** (`EtwasJonas/dhl-etikettensoftware`).
- Drucker kann **USB oder WLAN** verbunden sein – beides muss identisch funktionieren
  ( Auswahl über `lpstat`, Druck über `lp -d NAME`, CUPS abstrahiert die Verbindung).

## Akzeptanzkriterien

1. Auf dem Etikett erscheint **nur die Versandmarke** (keine A4-Restteile).
2. **Barcode/QR scannbar** – deshalb exakte Einpassung auf das Etikett ohne Verzerrung.
3. **Kein manueller Dialog** beim Alltagsdruck (Watch-Ordner macht es automatisch).
4. Verarbeitung verhindert **Doppeldruck** (Datei wandert nach `<Watch-Ordner>/gedruckt/`).
5. Druckfehler (z.B. Drucker offline) → nach 3 Versuchen nach `<Watch-Ordner>/fehlgeschlagen/`,
   kein Endlos-Spam, manuelles Nachdrucken möglich.
6. Programm läuft dauerhaft automatisch: systemd-User-Service startet bei Anmeldung,
   kein Ein-/Ausschalten nötig.

## Warum exakte Einpassung (Seitenverhältnis)

- A4-Hälfte: 210×148,5 mm → Verhältnis 1,414
- 4x6-Etikett: 100×150 mm → Verhältnis 1,5
- → Halbe-A4-Crop **ist nicht** 4x6. Deshalb: compose-Kette (crop → drehen →
  uniform skalieren → zentrieren), siehe docs/architektur.md §5.
- Drehung: Marke steht im A4 quer, Ziel-Etikett ist hochkant → `rotate = auto`
  (90°), in der Config auf 270 umstellbar falls verkehrt herum.

## Kalibrier-Prozess (6 Varianten, jeder Druck nur nach Bestätigung)

1. Top-Half exakt (pypdf)
2. `trim_top_mm = 5` (5 mm oben abgeschnitten)
3. `trim_bottom_mm = 5` (5 mm unten)
4. Ghostscript-Hardcrop (Fallback **ohne** Zielgröße – isoliert pypdf-Probleme)
5. Gedreht + exakt auf **100×150 mm** eingepasst
6. Gedreht + exakt auf **101,6×152,4 mm** (4"×6") eingepasst

Beste Variante → Werte in `~/.config/dhl-label/config.conf` unter `[crop]`
(`trim_top_mm`, `trim_bottom_mm`, `target_size_mm`, `rotate`). Vorschau ohne
Druck: `dhl-label crop DATEI.pdf [OUT.pdf]` (Optionen `--target --rotate
--trim-top --trim-bottom --gs`).

## Offene Punkte vom Nutzer (beim ersten echten Lauf klären)

- Ausgabe von `lpstat -p` und `lpoptions -p <DRUCKER> -l | grep -i size` auf dem Mint-PC
- Ergebnis der Kalibrierung (welche Variante passt, nötige Trims)
- Falls Namensfilter `versand|dhl|paket` nicht greift: tatsächlichen Dateinamen
  der DHL-PDF ermitteln und Filter anpassen

## Langfristiger Hinweis (bereits im README erwähnt)

DHL-**Geschäftskunden**portal kann Versandmarken direkt als 10×15-PDF ausgeben –
saubere Dauerlösung, falls Nutzer je Geschäftskunden-Zugang hat.
