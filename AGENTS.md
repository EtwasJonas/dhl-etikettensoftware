# AGENTS.md – Anweisungen für KI-Agenten (DHL Etikettensoftware)

Einstiegspunkt für KI-Agenten in diesem Repo. Wird von OpenCode automatisch gelesen.

## Projekt in einem Satz

Software, die aus dem A4-PDF des DHL-Privatkundenportals die Versandmarke croppt,
automatisch gedreht und **exakt** auf ein 4x6-Etikett (100×150 mm) einpasst (keine
Verzerrung – Barcode/QR müssen immer scannbar sein) und sie ohne Druckdialog auf
einen Vretti-Thermoetikettendrucker (USB **oder** WLAN) druckt. Watch-Ordner +
systemd-User-Service = „PDF herunterladen → druckt automatisch“.

## Docs-Übersicht (lies die relevante Datei im Volltext!)

| Datei | Inhalt |
|---|---|
| [docs/projekt.md](docs/projekt.md) | Anforderungen, Nutzer-Präferenzen, Akzeptanzkriterien, Kalibrier-Prozess |
| [docs/architektur.md](docs/architektur.md) | Datei-Zuständigkeiten, Verarbeitungs-Kette, Config-Format, Instanz-Layout auf Ziel-PC |
| [docs/status.md](docs/status.md) | **AKTUELLER Stand + offene Aufgaben (immer zuerst prüfen!)** |

## Eisernes Regeln

1. **Deutsch** – alle Nutzertexte (UI, README, Installer-Fragen, Fehlermeldungen) auf Deutsch, einsteigerfreundlich formuliert.
2. **Kein Terminal-Betrieb für den Nutzer** – Setup läuft per GUI (GTK3/PyGObject, auf Mint vorinstalliert; tkinter ist es NICHT). Terminal ist nur Fallback.
3. **Testdrucke nur nach Bestätigung** – im Terminal via input()-Prompt, in der GUI via Bestätigungsdialog.
4. **Seitenverhältnis heilig** – beim Einpassen auf die Zielgröße nur uniform skalieren (`s = min(tw/w, th/h)`), niemals beide Achsen unabhängig dehnen. QR-/Barcode-Scannbarkeit ist Akzeptanzkriterium.
5. **Kein BOM in Python-Dateien** – PowerShell `Set-Content -Encoding utf8` schreibt BOM → unter PS5.1 BOM-los schreiben (z.B. `[IO.File]::WriteAllText` mit `UTF8Encoding($false)`) oder edit-Tool nutzen.
6. **LF für Shell-Dateien** – `.gitattributes` erzwingt `eol=lf`; niemals CRLF in install.sh/uninstall.sh committen.
7. **pypdf lazy importieren** – `dhl_label.py` importiert pypdf erst in den Funktionen (CLI-Hilfe/`printers`/Parser müssen auch ohne pypdf laufen, z.B. auf Windows).
8. **Repo bleibt privat** – GitHub: `EtwasJonas/dhl-etikettensoftware` (gh CLI ist installiert + authentifiziert).

## Entwicklungsumgebung (Windows-PC, Ziel ist Linux Mint)

- Shell ist PowerShell; Bash gibt es unter `C:\Program Files\Git\bin\bash.exe` (`bash -n install.sh` = Syntaxcheck; Python-Syntaxcheck: `python -m py_compile <datei>`).
- pypdf für Tests: installiert unter `$env:TEMP\opencode\pylibs` → mit `$env:PYTHONPATH` nutzen; Test-PDFs erzeugen mit `PdfWriter().add_blank_page(...)`; Config für Tests via `$env:DHL_LABEL_CONFIG` auf eine Temp-Config zeigen lassen (BOM-frei schreiben!).
- **GTK/PyGObject ist auf Windows NICHT testbar** → `setup_gui.py` nur mit py_compile + sorgfältigem Lesen prüfen; echter GUI-Test nur auf dem Mint-PC.
- Bearbeite Dateien bevorzugt mit dem edit-Tool; Nach-neu-Schreiben via PowerShell nur BOM-frei.
- Umgebungswechsel beachten: Shell-Tool hieß früher `bash`, heißt jetzt `shell`.

## Quick-Referenz: wichtigste Befehle

```bash
# Ziel-PC (Mint) – Terminal-Fallback-Installation:
bash install.sh                     # interaktiv
# Ziel-PC – Befehle (Wrapper ~/.local/bin/dhl-label):
dhl-label watch|print|print-latest|crop|calibrate|show-config|printers|print-pdf
dhl-label --help
# Service:
systemctl --user status|restart|stop dhl-label
journalctl --user -u dhl-label -f
# Repo:
git add -A && git commit -m "..." && git push
gh repo view EtwasJonas/dhl-etikettensoftware --json isPrivate   # muss isPrivate:true bleiben
```

## Minimale Sanity-Checks vor jedem Push

1. `python -m py_compile dhl_label.py gui_helpers.py setup_gui.py`
2. `bash -n install.sh && bash -n uninstall.sh`
3. Bei PDF-Verarbeitungskette: Crop-/Compose-Test wie in docs/architektur.md §8 beschrieben (inkl. Uniform-Scale-Assert).
4. `git diff --stat` prüfen – keine unbeabsichtigten Dateien.
