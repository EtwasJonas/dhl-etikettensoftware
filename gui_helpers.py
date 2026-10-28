# -*- coding: utf-8 -*-
"""
gui_helpers.py – Reine Logik für den GUI-Setup-Assistenten (ohne GTK),
damit Parsing- und Befehls-Erzeugung separat getestet werden kann.
"""

import re
import shutil
import subprocess
from pathlib import Path

MM_TO_PT = 72.0 / 25.4


def run_cmd(cmd, timeout=15):
    """Führt ein Kommando aus, gibt (rc, stdout) zurück; Missing-Binary → (127, '')."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout or "")
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def parse_printers(lpstat_output):
    """lpstat -p → [(name, status_text)], Status ohne 'printer NAME'-Präfix."""
    printers = []
    for line in (lpstat_output or "").splitlines():
        line = line.strip()
        m = re.match(r"^(?:printer|Drucker)\s+(\S+)\s+(.*)$", line)
        if m:
            status = m.group(2).rstrip(".")
            printers.append((m.group(1), status))
    return printers


def list_printers():
    """[(name, status)] aller CUPS-Drucker (USB und WLAN/Netzwerk)."""
    _, out = run_cmd(["lpstat", "-p"])
    return parse_printers(out)


def parse_media(lpoptions_output):
    """lpoptions -p X -l → (sizes, default, raw_line); None, wenn keine Zeile."""
    for line in (lpoptions_output or "").splitlines():
        if re.search(r"pagesize|^media", line, re.IGNORECASE):
            raw = line.strip()
            _, _, rest = raw.partition(":")
            sizes = rest.split()
            default = None
            cleaned = []
            for s in sizes:
                if s.startswith("*"):
                    default = s[1:]
                    cleaned.append(s[1:])
                else:
                    cleaned.append(s)
            return cleaned, default, raw
    return None


def media_sizes(printer):
    result = parse_media(run_cmd(["lpoptions", "-p", printer, "-l"])[1])
    if result is None:
        return [], None, ""
    return result


def parse_size_mm(text):
    """'100x150' (mm) → (100.0, 150.0); ''/0 → None; ungültig → ValueError."""
    text = (text or "").strip().lower().replace(",", ".").replace("\u00d7", "x")
    if not text or text in ("0", "none", "aus", "off"):
        return None
    m = re.match(r"^(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)$", text)
    if not m:
        raise ValueError(f"Ungültige Größe: {text!r} – z.B. '100x150' (Breite x Höhe in mm)")
    return (float(m.group(1)), float(m.group(2)))


def build_install_cmd(install_sh, *, printer, media, target, watch_mode,
                      watch_dir, pattern, side):
    """Baut die Kommandozeile für install.sh (nicht-interaktiver Modus)."""
    cmd = ["bash", str(install_sh),
           "--printer", printer,
           "--media", media,
           "--target", target,
           "--watch-mode", watch_mode,
           "--watch-dir", watch_dir,
           "--pattern", pattern,
           "--side", side,
           "--no-calibrate",
           "--pkexec",
           "--non-interactive"]
    return cmd


def calibration_variants():
    """[(name, [CLI-Args für 'dhl-label crop'])] – 6 Kalibriervarianten."""
    return [
        ("1: obere Hälfte exakt", []),
        ("2: 5 mm oben abgeschnitten", ["--trim-top", "5"]),
        ("3: 5 mm unten abgeschnitten", ["--trim-bottom", "5"]),
        # --target "" ist Pflicht: sonst würde eine Zielgröße aus der config.conf
        # Vorrang haben und die Ghostscript-Variante wäre identisch zu Variante 1
        ("4: Ghostscript-Hardcrop (ohne Zielgröße)", ["--gs", "--target", ""]),
        ("5: gedreht + exakt 100x150 mm", ["--target", "100x150"]),
        ("6: gedreht + exakt 101,6x152,4 mm (4\"x6\")", ["--target", "101.6x152.4"]),
    ]


def build_crop_cmd(venv_python, dhl_label_py, src, out, variant_args):
    """Kommandozeile, um eine Kalibriervariante in eine PDF zu rendern."""
    return [str(venv_python), str(dhl_label_py), "crop", str(src), str(out)] + variant_args


def build_print_cmd(printer, media, pdf_path, extra_options=""):
    """lp-Befehl zum Drucken einer fertigen (gecroppten) PDF."""
    cmd = ["lp", "-d", printer, "-o", f"media={media}"]
    if extra_options and extra_options.strip():
        cmd += extra_options.split()
    cmd.append(str(pdf_path))
    return cmd


def check_environment():
    """Prüft Voraussetzungen; gibt (ok, meldungen[]) zurück."""
    problems = []
    if shutil.which("lpstat") is None:
        problems.append("CUPS-Druckdienst nicht gefunden (cups-client fehlt). "
                        "Bitte zuerst im Terminal ausführen:\n"
                        "  sudo apt install cups-client\nund dieses Setup neu starten.")
    if shutil.which("python3") is None:
        problems.append("Python 3 wurde nicht gefunden (python3).")
    return (len(problems) == 0, problems)


def read_installed_config(path="~/.config/dhl-label/config.conf"):
    """Liest die installierte Konfiguration (für die GUI-Kalibrierung)."""
    import configparser
    cp = configparser.ConfigParser()
    cp.read(str(Path(path).expanduser()), encoding="utf-8")

    def get(section, key, default=""):
        try:
            return cp[section][key]
        except KeyError:
            return default

    raw_watch = get("watch", "dir", default="~/Downloads")
    # Nur ~ expandieren; absolute Pfade unangetastet lassen (str(Path()) würde
    # sie sonst plattformabhängig umformen).
    watch_dir = str(Path(raw_watch).expanduser()) if raw_watch.startswith("~") else raw_watch

    return {
        "printer": get("printer", "name"),
        "media": get("printer", "media"),
        "extra_options": get("printer", "extra_options"),
        "watch_dir": watch_dir,
        "watch_mode": get("watch", "mode", default="downloads"),
        "filename_pattern": get("watch", "filename_pattern", default=""),
        "target_size_mm": get("crop", "target_size_mm"),
        "side": get("crop", "side", default="top"),
    }


def installed_state(path="~/.config/dhl-label/config.conf"):
    """Ist die Software bereits installiert? → (installed, config | None).
    Installiert = config.conf vorhanden UND Druckername eingetragen."""
    p = Path(path).expanduser()
    if not p.exists():
        return False, None
    cfg = read_installed_config(str(p))
    return (bool(cfg.get("printer")), cfg)
