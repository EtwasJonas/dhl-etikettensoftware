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
8. **Repo-Sichtbarkeit: öffentlich** – GitHub: `EtwasJonas/dhl-etikettensoftware` (gh CLI ist installiert + authentifiziert). Der Nutzer hat am 01.11.2026 explizit auf **public** umgestellt (zuvor privat). Sichtbarkeit NICHT ohne direkte Nutzeranweisung ändern.

## Entwicklungsumgebung (Windows-PC, Ziel ist Linux Mint)

- Shell ist PowerShell; Bash gibt es unter `C:\Program Files\Git\bin\bash.exe` (`bash -n install.sh` = Syntaxcheck; Python-Syntaxcheck: `python -m py_compile <datei>`).
- pypdf für Tests: installiert unter `$env:TEMP\opencode\pylibs` → mit `$env:PYTHONPATH` nutzen; Test-PDFs erzeugen mit `PdfWriter().add_blank_page(...)`; Config für Tests via `$env:DHL_LABEL_CONFIG` auf eine Temp-Config zeigen lassen (BOM-frei schreiben!).
- **GTK/PyGObject ist auf Windows NICHT testbar** → `setup_gui.py` nur mit py_compile + sorgfältigem Lesen prüfen; echter GUI-Test nur auf dem Mint-PC. Die **Windows-GUI (`setup_gui_win.py`, tkinter) ist dagegen hier voll testbar** (Smoketest: Konstruktor bauen + destroy, ohne mainloop/Fenster).
- Bearbeite Dateien bevorzugt mit dem edit-Tool; Nach-neu-Schreiben via PowerShell nur BOM-frei.
- Umgebungswechsel beachten: Shell-Tool hieß früher `bash`, heißt jetzt `shell`.

## Windows-11-Support (seit 11/2026)

- Plattform-Verzweigungen: `os.name == "nt"` → `win_backend.py` (GDI-Druck,
  Autostart, Watcher-Lock) + `setup_gui_win.py` (tkinter). Config unter
  `%APPDATA%\dhl-label\config.conf`, Log unter `%LOCALAPPDATA%\dhl-label\`.
- **Kein GTK, kein lp/gs, kein systemd unter Windows** – Ghostscript-Variante
  4 der Kalibrierung gibt es nur unter Linux (in GUI + Fehlermeldungen beachten).
- **Uniform-Scale gilt auch im Windows-Druckpfad** (`fit_rect` in
  win_backend.py) – Barcode-Scannbarkeit!
- Test-venv: `$env:TEMP\opencode\wenv` (pypdf, pywin32, pypdfium2, Pillow,
  pyinstaller). EXE-Build: `python -m PyInstaller dhl-label-win.spec --noconfirm`.
- windowed-EXE: PowerShell wartet nicht → `Start-Process -Wait -PassThru`;
  Prozesse nur mit `Stop-Process -Name dhl-label` beenden (onefile Parent/Child).
- "Microsoft Print to PDF" hängt bei StartDoc (modaler Dialog) → GDI-Tests
  ohne EndDoc; echten Drucktest nur am realen Vretti.
- CI `.github/workflows/windows-build.yml`: Tests unter Linux + Windows,
  EXE-Artefakt, Release-Anhang bei Tag `v*`. **GitHub Releases für die EXE
  nutzen** (Nutzer laden von dort).

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
gh repo view EtwasJonas/dhl-etikettensoftware --json isPrivate   # Sichtbarkeit pruefen (aktuell: public, nicht aendern)
# Release (EXE fuer Windows-Nutzer):
git tag vX.Y.Z && git push origin vX.Y.Z   # CI baut EXE + haengt sie ans Release (contents:write)
gh release view vX.Y.Z --json assets       # Asset pruefen (aktuell live: v1.1.0)
```

## Minimale Sanity-Checks vor jedem Push

1. `python -m py_compile dhl_label.py gui_helpers.py setup_gui.py`
2. `bash -n install.sh && bash -n uninstall.sh`
3. Bei PDF-Verarbeitungskette: Crop-/Compose-Test wie in docs/architektur.md §8 beschrieben (inkl. Uniform-Scale-Assert).
4. `git diff --stat` prüfen – keine unbeabsichtigten Dateien.
