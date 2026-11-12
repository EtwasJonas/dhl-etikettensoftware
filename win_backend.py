# -*- coding: utf-8 -*-
"""
win_backend.py – Windows-Backend der DHL-Etikettensoftware (nur unter Windows aktiv).

Enthält:
  - GDI-Druckpfad: gecroppte PDF → Rasterbild (pypdfium2) → Windows-Druckertreiber
    (win32print/win32ui + Pillow ImageWin). Kein Druckdialog, Uniform-Scale auch
    beim Einpassen in den druckbaren Bereich (Barcode-Scannbarkeit!).
  - Drucker-/Papierformate-Auflistung über die Windows-Druck-API.
  - Autostart-Verknüpfung (Startmenü-Autostart-Ordner, kein Admin nötig).
  - Watcher-Einzelinstanz-Lock + Log-Ordner.

Wichtig: Top-Level nur Standardbibliothek – das Modul muss auch unter Linux
importierbar sein (Tests, gemeinsame Hilfsfunktionen). pywin32/pypdfium2/PIL
werden lazy innerhalb der Funktionen importiert.
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

APP_NAME = "dhl-label"
AUTOSTART_NAME = "DHL-Etiketten-Autostart.lnk"

# Rasterqualität: 600 dpi genügt locker für 203/300-dpi-Thermoköpfe und
# bleibt auch bei 100x150 mm RAM-/Zeit-technisch harmlos.
RENDER_DPI = 600

# Windows-PRINTER_STATUS-Codes (Auszug) → Klartext
_PRINTER_STATUS = {
    0x00000000: "Bereit",
    0x00000001: "Angehalten",
    0x00000002: "Fehler",
    0x00000004: "Wird gelöscht",
    0x00000008: "Papierstau",
    0x00000010: "Kein Papier",
    0x00000020: "Manuelle Zufuhr",
    0x00000040: "Papierproblem",
    0x00000080: "Offline",
    0x00000100: "Nicht verfügbar",
    0x00000200: "Beschäftigt",
    0x00000400: "Wird gedruckt",
    0x00000800: "Initialisiert",
    0x00001000: "Wartet auf Wärme",
    0x00002000: "Verarbeitung",
    0x00004000: "Energie sparen",
}


# ------------------------------------------------------------------ Pfade/Log

def app_data_dir():
    """%LOCALAPPDATA%\\dhl-label (Log, Lock); Fallback auf %APPDATA% bzw. Home."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_NAME


def log_file():
    return app_data_dir() / "dhl-label.log"


def startup_dir():
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def autostart_path():
    return startup_dir() / AUTOSTART_NAME


def autostart_exists():
    return autostart_path().exists()


# ------------------------------------------------------------- Geometrie

def fit_rect(img_w, img_h, area_w, area_h):
    """Berechnet ein zentriertes Ziel-Rechteck, das das Bild UNIFORM skaliert
    in den (druckbaren) Bereich einpasst – nie beide Achsen unabhängig!
    → (x, y, w, h) im Koordinatensystem des Bereichs."""
    scale = min(area_w / float(img_w), area_h / float(img_h))
    w = img_w * scale
    h = img_h * scale
    x = (area_w - w) / 2.0
    y = (area_h - h) / 2.0
    return x, y, w, h


def _page_size_mm(dc):
    """Physische Seitengröße eines Drucker-DC in mm → (w, h); (None, None) bei Fehlern."""
    try:
        import win32con

        lp_x = dc.GetDeviceCaps(win32con.LOGPIXELSX) or 0
        lp_y = dc.GetDeviceCaps(win32con.LOGPIXELSY) or 0
        phys_w = dc.GetDeviceCaps(win32con.PHYSICALWIDTH)
        phys_h = dc.GetDeviceCaps(win32con.PHYSICALHEIGHT)
        if lp_x <= 0 or lp_y <= 0 or phys_w <= 0 or phys_h <= 0:
            return None, None
        return (phys_w / lp_x * 25.4, phys_h / lp_y * 25.4)
    except Exception:
        return None, None


def render_pdf_first_page(pdf_path, dpi=RENDER_DPI):
    """Rendert die erste PDF-Seite als PIL-Image (lazy imports)."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        page = doc[0]
        bitmap = page.render(scale=float(dpi) / 72.0)
        return bitmap.to_pil()
    finally:
        doc.close()


# Für Thermotransfer: harte Schwarz/Weiß-Pixel statt Grau-Dithering.
THERMAL_SUPERSAMPLE = 4
THERMAL_THRESHOLD = 170


def render_pdf_thermal(pdf_path, native_dpi, factor=THERMAL_SUPERSAMPLE,
                       threshold=THERMAL_THRESHOLD):
    """Rendert mit facher Auflösung, mittelt dann per BOX-Filter auf die
    native Drucker-Auflösung herunter und setzt abschließend einen
    Schwellwert auf Schwarz/Weiß. Ergebnis: vollere Striche, keine
    Dithering-Artefakte."""
    from PIL import Image

    image = render_pdf_first_page(pdf_path, native_dpi * factor)
    width = max(1, round(image.width / factor))
    height = max(1, round(image.height / factor))
    gray = image.resize((width, height), Image.Resampling.BOX).convert("L")
    return gray.point(lambda v: 0 if v < threshold else 255)


# ------------------------------------------------------------- Drucker-API

def list_printers():
    """[(name, status_text)] aller in Windows eingerichteten Drucker
    (lokal installiert inkl. USB-Treiber + verbundene Netzwerkdrucker)."""
    import win32print

    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    result = []
    entries = win32print.EnumPrinters(flags, None, 4)
    if not entries:
        return result
    if isinstance(entries[0], dict):  # pywin32 ≥ r300: Liste von Dicts
        names = [entry.get("pPrinterName", "") for entry in entries]
    else:  # ältere pywin32: Tuples (flags, name, port)
        names = [entry[1] for entry in entries]
    for name in names:
        if not name:
            continue
        status_text = "Bereit"
        try:
            handle = win32print.OpenPrinter(name)
            try:
                status = int(win32print.GetPrinter(handle, 2).get("Status", 0) or 0)
                status_text = _PRINTER_STATUS.get(status, f"Status {status:#x}")
            finally:
                win32print.ClosePrinter(handle)
        except Exception:
            pass
        result.append((name, status_text))
    return result


def printers_text():
    """Mehrzeiliger Klartext der Druckerliste (CLI/printers-Befehl)."""
    lines = ["Drucker in Windows (lokal installiert / Netzwerk):"]
    printers = list_printers()
    if not printers:
        lines.append("  (keine Drucker eingerichtet)")
    for name, status in printers:
        lines.append(f"  {name}  [{status}]")
    lines.append("")
    lines.append("USB-Drucker: nach dem Anstecken richtet Windows den Treiber ein.")
    lines.append("Papierformat des Treibers ändern: Einstellungen → Drucker → Druckereinstellungen.")
    return "\n".join(lines)


def _printer_info(printer_name):
    import win32print

    handle = win32print.OpenPrinter(printer_name)
    try:
        info = win32print.GetPrinter(handle, 2)
        return handle, info
    except Exception:
        win32print.ClosePrinter(handle)
        raise


def paper_sizes(printer_name):
    """[(paper_id, name)] Papierformate aus dem Treiber + ID des Standards.
    Treiber ohne Formate → ([], None)."""
    import win32con
    import win32print

    handle, info = _printer_info(printer_name)
    try:
        port = info.get("pPortName") or ""
        devmode = info.get("pDevMode")
        default_id = getattr(devmode, "PaperSize", None)
        try:
            names = win32print.DeviceCapabilities(
                printer_name, port, win32con.DC_PAPERNAMES)
            ids = win32print.DeviceCapabilities(
                printer_name, port, win32con.DC_PAPERS)
        except Exception:
            return [], None
        papers = []
        for paper_id, name in zip(ids, names):
            name = str(name).rstrip("\x00").strip()
            if name:
                papers.append((int(paper_id), name))
        return papers, (int(default_id) if default_id else None)
    finally:
        win32print.ClosePrinter(handle)


def paper_sizes_text(printer_name):
    papers, default_id = paper_sizes(printer_name)
    lines = [f"Papierformate von {printer_name!r}:"]
    if not papers:
        lines.append("  (der Treiber meldet keine Formate – Standardgröße wird genutzt)")
    for paper_id, name in papers:
        marker = "  *" if paper_id == default_id else "   "
        lines.append(f"{marker} {paper_id}: {name}")
    return "\n".join(lines)


def _norm_paper(text):
    """'User Defined 100x150mm' → 'userdefined100x150mm' (für Fuzzy-Match)."""
    return re.sub(r"[^0-9a-z]", "", str(text or "").lower())


def _match_paper_id(papers, wanted):
    """Findet Papier-ID: erst exakt, dann Fuzzy (Namen ohne Sonderzeichen,
    Substring in beide Richtungen – findet '100x150' in 'User Defined
    100x150mm' und '4x6' in '4x6in')."""
    if not wanted:
        return None
    target = _norm_paper(wanted)
    if not target:
        return None
    for paper_id, name in papers:
        if _norm_paper(name) == target:
            return paper_id
    for paper_id, name in papers:
        cand = _norm_paper(name)
        if target in cand or (len(cand) >= 3 and cand in target):
            return paper_id
    return None


def _prepare_devmode(printer_name, paper_wanted, landscape, target_mm=None):
    """Holt den DEVMODE des Treibers, setzt Papierformat + Ausrichtung und
    normalisiert ihn über DocumentProperties. Gibt (devmode, papier_angewendet)
    zurück; bei Fehlern (None, False).

    Mit target_mm (tw, th) wird die EXAKTE Etikettengröße als Custom-Size
    gesetzt (DMPAPER_USER + PaperWidth/PaperLength in zehntel mm) – wichtig,
    weil Treiber-Vorgaben wie "4 x 6" größer sein können als das echte Etikett
    (SN 420B: 104,2 mm statt 101,6 mm → Inhalt rutscht seitlich)."""
    import win32con
    import win32print

    handle, info = _printer_info(printer_name)
    try:
        port = info.get("pPortName") or ""
        devmode = info.get("pDevMode")
        applied = False
        if devmode is None:
            return None, False
        if target_mm and isinstance(target_mm, (tuple, list)):
            tw, th = float(target_mm[0]), float(target_mm[1])
            devmode.PaperSize = win32con.DMPAPER_USER
            # Papier selbst ist stets schmal × lang; Orientation entscheidet,
            # ob die Seite hochkant (tw<th) oder quer (tw>th) bedruckt wird.
            devmode.PaperWidth = int(round(min(tw, th) * 10))
            devmode.PaperLength = int(round(max(tw, th) * 10))
            devmode.Orientation = 2 if tw > th else 1
            applied = True
        else:
            papers, _default = ([], None)
            try:
                papers, _default = paper_sizes(printer_name)
            except Exception:
                pass
            paper_id = _match_paper_id(papers, paper_wanted)
            if paper_id:
                devmode.PaperSize = paper_id
                applied = True
            elif (paper_wanted or "").strip():
                log(f"Hinweis: Papierformat {paper_wanted!r} nicht im Treiber gefunden – "
                    "Standardformat des Treibers wird verwendet.")
            devmode.Orientation = 2 if landscape else 1  # 2 = Landscape
        result = win32print.DocumentProperties(
            0, handle, printer_name, devmode, devmode,
            win32con.DM_IN_BUFFER | win32con.DM_OUT_BUFFER)
        if hasattr(result, "PaperSize"):  # je nach pywin32-Version Objekt oder int
            devmode = result
        return devmode, applied
    finally:
        win32print.ClosePrinter(handle)


def log(msg):
    """Konsolen-/Datei-Log wie dhl_label.log (hier dupliziert, um Zirkelimport
    zu vermeiden; schreibt zusätzlich in die Windows-Logdatei)."""
    line = str(msg)
    try:
        print(line, flush=True)
    except (OSError, AttributeError, ValueError):
        pass
    append_log_file(line)


def append_log_file(line):
    """Hängt an %LOCALAPPDATA%\\dhl-label\\dhl-label.log an (max. ~1 MB, dann .old).
    Jede Zeile bekommt einen Zeitstempel – ohne den lässt sich ein „wohin ist
    meine PDF gegangen“ hinterher nicht mehr nachvollziehen."""
    try:
        path = log_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if path.stat().st_size > 1_000_000:
                old = path.with_suffix(".old")
                try:
                    old.unlink()
                except OSError:
                    pass
                path.replace(old)
        except OSError:
            pass
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        parts = str(line).splitlines() or [""]
        stamped = f"[{stamp}] {parts[0]}" + \
            ("".join("\n" + p for p in parts[1:]))
        with open(path, "a", encoding="utf-8", errors="replace") as fh:
            fh.write(stamped + "\n")
    except OSError:
        pass


def print_pdf_windows(pdf_path, cfg):
    """Druckt eine fertig aufbereitete PDF (exakt Etikettengröße) still über
    den Windows-Druckertreiber. Gibt True bei Erfolg zurück.

    - Mit target_size_mm: Custom-Size exakt auf die Etikettengröße
      (Treiber-"4 x 6" kann z.B. 104,2 mm statt 101,6 mm breit sein).
    - Rendert in der Drucker-nativen Auflösung (LOGPIXELS) → 1:1-Pixel,
      kein Resampling (Barcode-Qualität).
    - Zentriert auf der physischen Seite (asymmetrische Treiber-Ränder
      verschieben den Inhalt nicht)."""
    from PIL import ImageWin

    import win32con
    import win32gui
    import win32print
    import win32ui

    printer_name = (cfg.printer or "").strip()
    if not printer_name:
        log("Kein Druckername in der Konfiguration ([printer] name).")
        return False

    target_mm = getattr(cfg, "target_mm", None)
    if not isinstance(target_mm, (tuple, list)):
        target_mm = None  # nur eingepasste (fertige) Etiketten-Seiten nutzen Custom-Size

    def create_dc(devmode):
        try:
            return win32ui.CreateDCFromHandle(
                win32gui.CreateDC("WINSPOOL", printer_name, devmode))
        except Exception as exc:
            if devmode is not None:
                log(f"Drucker-DC mit Treibereinstellungen fehlgeschlagen ({exc}) – "
                    "zweiter Versuch mit Standardeinstellungen.")
                try:
                    return win32ui.CreateDCFromHandle(
                        win32gui.CreateDC("WINSPOOL", printer_name, None))
                except Exception as exc2:
                    log(f"Drucker {printer_name!r} nicht erreichbar: {exc2}")
            else:
                log(f"Drucker {printer_name!r} nicht erreichbar: {exc}")
            return None

    def devmode_for(use_target):
        landscape_hint = use_target is not None and use_target[0] > use_target[1]
        try:
            return _prepare_devmode(printer_name, getattr(cfg, "media", ""),
                                    landscape_hint, use_target)
        except Exception as exc:
            log(f"Hinweis: Treibereinstellungen nicht lesbar ({exc}) – "
                "Standard des Druckers wird genutzt.")
            return (None, False)

    dc = None
    try:
        # 1) DEVMODE: bevorzugt Custom-Size = exakte Zielgröße
        devmode, _applied = devmode_for(target_mm)
        dc = create_dc(devmode)
        if dc is None:
            return False

        # 2) Seitengröße gegen Ziel prüfen (Treiber könnte Size verwerfen)
        if target_mm:
            page_w, page_h = _page_size_mm(dc)
            if page_w is None or abs(page_w - target_mm[0]) > 1.0 or \
                    abs(page_h - target_mm[1]) > 1.0:
                log(f"Hinweis: Treiber akzeptiert Custom-Size nicht "
                    f"(Seite {page_w}x{page_h} statt {target_mm[0]}x{target_mm[1]} mm) – "
                    "Fallback auf Papierformat des Treibers.")
                dc.DeleteDC()
                devmode, _applied = devmode_for(None)
                dc = create_dc(devmode)
                if dc is None:
                    return False

        # 3) In Drucker-nativer Auflösung rendern (Thermo: Supersample +
        #    BOX-Downsampling + Schwellwert → harte, vollere Pixel)
        dpi = max(150, dc.GetDeviceCaps(win32con.LOGPIXELSX) or RENDER_DPI)
        try:
            image = render_pdf_thermal(pdf_path, dpi)
        except Exception as exc:
            log(f"PDF konnte nicht gerendert werden: {exc}")
            return False
        log(f"Drucke an Windows-Drucker {printer_name!r} "
            f"({image.width}x{image.height} px bei {dpi} dpi) ...")

        dc.StartDoc(f"DHL-Etikett – {Path(pdf_path).name}")
        dc.StartPage()
        try:
            phys_w = dc.GetDeviceCaps(win32con.PHYSICALWIDTH)
            phys_h = dc.GetDeviceCaps(win32con.PHYSICALHEIGHT)
            off_x = dc.GetDeviceCaps(win32con.PHYSICALOFFSETX)
            off_y = dc.GetDeviceCaps(win32con.PHYSICALOFFSETY)
            area_w = dc.GetDeviceCaps(win32con.HORZRES)
            area_h = dc.GetDeviceCaps(win32con.VERTRES)
            if phys_w <= 0 or phys_h <= 0:
                raise RuntimeError(f"Drucker meldet keine Seitengröße ({phys_w}x{phys_h})")
            # Uniform einpassen (kein Verzerren!). Sonderfall: Bild == Seitengröße
            # (natives Rendering der exakten Etikettenseite) → 1:1 am Seiten-
            # ursprung zeichnen, dann entspricht der Druck exakt der PDF-Geometrie.
            # Sonst: auf der PHYSISCHEN Seite zentrieren, innerhalb des
            # druckbaren Bereichs geklemmt.
            x, y, w, h = fit_rect(image.width, image.height, area_w, area_h)
            if image.width == phys_w and image.height == phys_h:
                dest = (0, 0, phys_w, phys_h)
            else:
                x = min(max((phys_w - w) / 2.0 - off_x, 0.0), max(0.0, area_w - w))
                y = min(max((phys_h - h) / 2.0 - off_y, 0.0), max(0.0, area_h - h))
                dest = (int(off_x + x), int(off_y + y),
                        int(off_x + x + w), int(off_y + y + h))
            dib = ImageWin.Dib(image)
            dib.draw(dc.GetHandleOutput(), dest)
        finally:
            dc.EndPage()
        dc.EndDoc()
    except Exception as exc:
        try:
            dc.AbortDoc()
        except Exception:
            pass
        log(f"Druck fehlgeschlagen: {exc}")
        return False
    finally:
        try:
            if dc is not None:
                dc.DeleteDC()
        except Exception:
            pass
    log("Druckauftrag an den Drucker übergeben.")
    return True


def show_text_dialog(title, text):
    """Zeigt Text in einem Dialogfenster (für windowed-EXE ohne Konsole)."""
    import tkinter as tk
    from tkinter import messagebox

    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(title, text, parent=root)
        root.destroy()
    except Exception as exc:
        append_log_file(f"Dialog nicht möglich: {exc}\n{text}")


# ------------------------------------------------------------- Watcher-Lock

def _pid_alive(pid):
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return False
    exit_code = ctypes.c_ulong()
    ok = kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code))
    kernel.CloseHandle(handle)
    return bool(ok) and exit_code.value == STILL_ACTIVE


def watcher_running():
    """PID aus dem Lock lesen und prüfen, ob der Prozess noch lebt."""
    try:
        pid = int((app_data_dir() / "watcher.lock").read_text(encoding="ascii").strip())
        return _pid_alive(pid), pid
    except Exception:
        return False, None


def acquire_watch_lock():
    """Einzelinstanz-Schutz für den Watcher (verhindert Doppeldruck).
    → (erfolg, pid_des_läufers)."""
    running, pid = watcher_running()
    if running:
        return False, pid
    path = app_data_dir() / "watcher.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        fh.write(str(os.getpid()))
    return True, os.getpid()


def release_watch_lock():
    try:
        path = app_data_dir() / "watcher.lock"
        if int(path.read_text(encoding="ascii").strip()) == os.getpid():
            path.unlink()
    except Exception:
        pass


# ------------------------------------------------------------- Autostart

def _shortcut_target():
    """(Ziel, Argumente, Icon, Arbeitsverzeichnis) für die Autostart-Verknüpfung."""
    if getattr(sys, "frozen", False):  # PyInstaller-EXE
        exe = installed_exe_path() or Path(sys.executable).resolve()
        return str(exe), "watch", str(exe), str(exe.parent)
    base = Path(__file__).resolve().parent
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    interpreter = pythonw if pythonw.exists() else Path(sys.executable)
    icon = base / "icon.ico"
    return (str(interpreter), f'"{base / "dhl_label.py"}" watch',
            str(icon) if icon.exists() else str(interpreter), str(base))


def install_dir():
    """Installationsordner der EXE: %LOCALAPPDATA%\\DHL-Etiketten."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "DHL-Etiketten"


def install_exe_copy():
    """Kopiert die laufende (frozen) EXE in den Installationsordner, damit die
    Autostart-Verknüpfung nicht auf Downloads/Desktop zeigt. Kopiert nur bei
    geänderter Größe (Update). → Pfad der installierten EXE oder None."""
    if not getattr(sys, "frozen", False):
        return None
    try:
        import shutil

        source = Path(sys.executable)
        target_dir = install_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        if (not target.exists()
                or target.stat().st_size != source.stat().st_size):
            shutil.copy2(source, target)
        return target
    except Exception:
        return None


def installed_exe_path():
    """Installierte EXE (falls vorhanden) – bevorzugtes Autostart-Ziel."""
    if getattr(sys, "frozen", False):
        candidate = install_dir() / Path(sys.executable).name
        if candidate.exists():
            return candidate
    return None


def create_autostart_shortcut():
    """Erstellt die Verknüpfung im Autostart-Ordner (kein Admin nötig)."""
    import win32com.client  # noqa: F401 (pywin32 COM)

    shell = win32com.client.Dispatch("WScript.Shell")
    target, args, icon, workdir = _shortcut_target()
    shortcut = shell.CreateShortCut(str(autostart_path()))
    shortcut.TargetPath = target
    shortcut.Arguments = args
    shortcut.WorkingDirectory = workdir
    shortcut.IconLocation = f"{icon},0"
    shortcut.save()
    return autostart_path()


def remove_autostart_shortcut():
    try:
        autostart_path().unlink()
        return True
    except FileNotFoundError:
        return False


# ------------------------------------------------------------- Prozesse

def watcher_exe_name():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).name
    return "pythonw.exe"


def kill_watcher():
    """Beendet einen laufenden Watcher (frozen: nach EXE-Name; sonst PID aus Lock).
    Wartet danach kurz, bis der Prozess wirklich weg ist – sonst kann ein
    direkt danach gestarteter neuer Watcher denken, der alte lebe noch, und
    sich sofort wieder beenden (→ kein Watcher, obwohl die GUI „gestartet“
    meldet)."""
    running, pid = watcher_running()
    if running and pid and pid != os.getpid():
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           capture_output=True, timeout=15)
        except Exception:
            pass
        if not _wait_watcher_gone(6.0):
            log(f"Achtung: Watcher (PID {pid}) ließ sich nicht beenden.")
            return False
        return True
    if getattr(sys, "frozen", False):
        try:
            subprocess.run(["taskkill", "/IM", watcher_exe_name(), "/F"],
                           capture_output=True, timeout=15)
            return True
        except Exception:
            return False
    return False


def _wait_watcher_gone(timeout=6.0):
    """Wartet, bis watcher_running() False meldet (Taskkill braucht einen
    Moment, bis das-Prozess-Handle komplett weg ist). → True, wenn weg."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        running, _pid = watcher_running()
        if not running:
            return True
        time.sleep(0.2)
    return not watcher_running()[0]


def spawn_watch_detached():
    """Startet den Watcher losgelöst von der GUI (überlebt GUI-Ende)."""
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "watch"]
        cwd = str(Path(sys.executable).parent)
    else:
        base = Path(__file__).resolve().parent
        pythonw = Path(sys.executable).parent / "pythonw.exe"
        interpreter = pythonw if pythonw.exists() else sys.executable
        cmd = [str(interpreter), str(base / "dhl_label.py"), "watch"]
        cwd = str(base)
    subprocess.Popen(cmd, creationflags=flags, close_fds=True, cwd=cwd)
