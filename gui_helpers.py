# -*- coding: utf-8 -*-
"""
gui_helpers.py – Reine Logik für den GUI-Setup-Assistenten (ohne GTK),
damit Parsing- und Befehls-Erzeugung separat getestet werden kann.
"""

import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

MM_TO_PT = 72.0 / 25.4


def defaults_file_candidates():
    """Suchpfade für defaults.conf: EXE-Bundle, Repo-Ordner, Linux-Installation."""
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)  # PyInstaller-Entpackordner
    if meipass:
        candidates.append(Path(meipass) / "defaults.conf")
    candidates.append(Path(__file__).resolve().parent / "defaults.conf")
    candidates.append(Path("~/.local/share/dhl-label/defaults.conf").expanduser())
    return candidates


def load_defaults():
    """Werks-Defaults (vorkalibriert) aus defaults.conf → dict (Sektion [crop])
    oder {} falls die Datei fehlt/unlesbar ist. NIE wirft – Setup darf damit
    Formular-Vorbefüllung machen."""
    import configparser

    for candidate in defaults_file_candidates():
        try:
            if not candidate.exists():
                continue
            cp = configparser.ConfigParser()
            cp.read(str(candidate), encoding="utf-8")
            if cp.has_section("crop"):
                return {key: cp["crop"][key] for key in cp["crop"]}
        except Exception:
            continue
    return {}


def default_config_path():
    """Plattformabhängiger Standardpfad der config.conf.
    DHL_LABEL_CONFIG überschreibt (auch für Tests)."""
    env = os.environ.get("DHL_LABEL_CONFIG")
    if env:
        return Path(env).expanduser()
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "dhl-label" / "config.conf"
    return Path("~/.config/dhl-label/config.conf").expanduser()


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
    """[(name, status)] aller eingerichteten Drucker (USB und WLAN/Netzwerk)
    – Linux via CUPS (lpstat), Windows via Druck-API."""
    if os.name == "nt":
        from win_backend import list_printers as win_list_printers

        return win_list_printers()
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
    """Medien-/Papierformate eines Druckers → (sizes, default, raw_line).
    Linux: CUPS-Seitengrößen (lpoptions); Windows: Papierformate des Treibers."""
    if os.name == "nt":
        from win_backend import paper_sizes

        papers, default_id = paper_sizes(printer)
        names = [name for _pid, name in papers]
        default = next((name for pid, name in papers if pid == default_id), None)
        return names, default, f"Windows-Treiber ({len(names)} Formate)"
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


def parse_trim_mm(text):
    """Zuschnitt-Angabe (mm) → float; ''/0 → 0.0; Komma erlaubt; sonst ValueError.
    (Negativ/NaN/inf werden abgelehnt – es wird nur abgeschnitten.)"""
    value = (text or "").strip().replace(",", ".")
    if not value or value in ("0", "0.0"):
        return 0.0
    try:
        result = float(value)
    except ValueError:
        raise ValueError(f"Ungültiger Zuschnitt: {text!r} – Zahl in mm, z.B. 5 oder 2,5")
    if not math.isfinite(result) or result < 0:
        raise ValueError("Zuschnitt muss eine Zahl ≥ 0 sein (mm, die abgeschnitten werden).")
    return result


def build_install_cmd(install_sh, *, printer, media, target, watch_mode,
                      watch_dir, pattern, side,
                      trim_top=0.0, trim_bottom=0.0, trim_left=0.0, trim_right=0.0,
                      profile=""):
    """Baut die Kommandozeile für install.sh (nicht-interaktiver Modus).

    profile: aktives Profil; nur bei gesetztem Namen wird --profile übergeben
    (leer = install.sh entscheidet: aktives Profil der alten Config, sonst
    „Standard“)."""
    cmd = ["bash", str(install_sh),
           "--printer", printer,
           "--media", media,
           "--target", target,
           "--trim-top", f"{trim_top:g}",
           "--trim-bottom", f"{trim_bottom:g}",
           "--trim-left", f"{trim_left:g}",
           "--trim-right", f"{trim_right:g}",
           "--watch-mode", watch_mode,
           "--watch-dir", watch_dir,
           "--pattern", pattern,
           "--side", side]
    if (profile or "").strip():
        cmd += ["--profile", profile.strip()]
    cmd += ["--no-calibrate", "--pkexec", "--non-interactive"]
    return cmd


# ------------------------------------------------------------------ Profile
#
# Profile sind gespeicherte Kalibrier-Sätze (Etikettengröße, Zuschnitt,
# Position der Marke, Rotation) in der config.conf – je eine Sektion
# [profile:NAME]. Das Profil „Standard“ enthält die Werks-Kalibrierung
# (defaults.conf) und ist immer vorhanden. Die WIRKSAMEN Werte liegen
# weiterhin in [crop] – ein Profilwechsel kopiert die Werte dorthin.

FACTORY_PROFILE = "Standard"      # Werks-Profil (nie löschbar/umbenennbar)
PROFILE_PREFIX = "profile:"       # Sektions-Präfix in der config.conf
PROFILE_KEYS = ("side", "trim_top_mm", "trim_bottom_mm", "trim_left_mm",
                "trim_right_mm", "target_size_mm", "rotate")
_TRIM_KEYS = ("trim_top_mm", "trim_bottom_mm", "trim_left_mm", "trim_right_mm")


def valid_profile_name(name):
    """Profilname für eine config.conf-Sektion zulässig? (max. 40 Zeichen,
    keine Sondersyntax [ ] : = , keine Steuerzeichen)."""
    name = (name or "").strip()
    if not name or len(name) > 40:
        return False
    for ch in "[]:=\r\n\t":
        if ch in name:
            return False
    return True


def normalize_profile_values(raw):
    """Profil-Werte vervollständigen/formatieren: alle PROFILE_KEYS als
    Strings, Zuschnitt numerisch formatiert („16,24“ → „16.24“), fehlende
    side/rotate → top/auto. Nie werfen – für GUI-Vorbefüllung."""
    values = {}
    for key in PROFILE_KEYS:
        value = str((raw or {}).get(key, "") or "").strip()
        if key in _TRIM_KEYS:
            try:
                value = f"{float(value.replace(',', '.')):g}" if value else "0"
            except ValueError:
                value = "0"
        values[key] = value
    if not values["side"]:
        values["side"] = "top"
    if not values["rotate"]:
        values["rotate"] = "auto"
    return values


def factory_profile_values():
    """Werks-Kalibrierung (defaults.conf) als Profil-Werte; None, wenn die
    Datei fehlt/unlesbar ist."""
    defaults = load_defaults()
    if not defaults:
        return None
    return normalize_profile_values(defaults)


def trims_are_zero(values):
    """Sind alle vier Zuschnitt-Werte 0 (= nie kalibriert)?"""
    for key in _TRIM_KEYS:
        try:
            if abs(float(str((values or {}).get(key, "0")).replace(",", "."))) > 1e-9:
                return False
        except (ValueError, TypeError):
            return False
    return True


def profile_values_equal(a, b):
    """Zwei Profil-Wert-Sätze inhaltlich gleich? (Zuschnitt numerisch,
    side/rotate groß-/klein-unabhängig, Zielgröße „“ == „0“.)"""
    a = normalize_profile_values(a)
    b = normalize_profile_values(b)
    for key in PROFILE_KEYS:
        va, vb = a[key], b[key]
        if key in _TRIM_KEYS:
            try:
                equal = abs(float(va.replace(",", ".")) -
                            float(vb.replace(",", "."))) < 1e-9
            except ValueError:
                equal = va == vb
            if not equal:
                return False
        elif key in ("side", "rotate"):
            if va.lower() != vb.lower():
                return False
        else:  # target_size_mm
            try:
                if parse_size_mm(va) != parse_size_mm(vb):
                    return False
            except ValueError:
                if va != vb:
                    return False
    return True


def read_profiles(path=None):
    """Profile aus der config.conf lesen → ({name: werte}, aktiver Name).

    Das Werks-Profil „Standard“ fehlt nie: fehlt es in der Datei, wird es
    aus defaults.conf (oder neutral) ergänzt und steht in der Liste zuerst.
    Datei fehlt/unlesbar → ({Standard: Werks-Werte}, "")."""
    import configparser

    p = Path(path) if path else default_config_path()
    profiles = {}
    active = ""
    try:
        cp = configparser.ConfigParser()
        cp.read(str(p), encoding="utf-8")
        if cp.has_section("crop"):
            active = (cp["crop"].get("profile", "") or "").strip()
        for section in cp.sections():
            if not section.startswith(PROFILE_PREFIX):
                continue
            name = section[len(PROFILE_PREFIX):].strip()
            if valid_profile_name(name) and len(cp.options(section)) > 0:
                profiles[name] = normalize_profile_values(dict(cp[section]))
    except Exception:
        profiles = {}
        active = ""
    if FACTORY_PROFILE not in profiles:
        factory = factory_profile_values()
        profiles[FACTORY_PROFILE] = factory if factory is not None \
            else normalize_profile_values({})
    ordered = {FACTORY_PROFILE: profiles[FACTORY_PROFILE]}
    for name, values in profiles.items():
        if name != FACTORY_PROFILE:
            ordered[name] = values
    return ordered, active


def resolve_startup_values(crop_values, profiles, active):
    """Welche Werte sollen beim GUI-Start im Formular stehen?

    Behebt das „Zweit-PC zeigt überall 0“-Problem: eine config.conf, die vor
    v1.2.0 geschrieben wurde, enthielt nie die Werks-Kalibrierung. Regeln:
      1. Aktives Profil vorhanden → dessen Werte.
      2. Kein Profil, aber [crop] entspricht der Werks-Kalibrierung → Standard.
      3. Kein Profil und unkalibriert (alle Zuschnitte 0) → Werks-Werte
         vorausfüllen (mit Hinweis).
      4. Sonst → aktuelle [crop]-Werte, keine Profil-Auswahl (mit Hinweis).

    → (werte, ausgewählter Profilname (oder ""), Hinweis (oder None))"""
    active = (active or "").strip()
    if active and active in profiles:
        return dict(profiles[active]), active, None
    current = normalize_profile_values(crop_values)
    standard = profiles.get(FACTORY_PROFILE)
    if standard is None:
        standard = factory_profile_values() or normalize_profile_values({})
    if profile_values_equal(current, standard):
        return dict(standard), FACTORY_PROFILE, None
    if trims_are_zero(current):
        return (dict(standard), FACTORY_PROFILE,
                "Alte Einstellungen gefunden (Zuschnitt überall 0) – die "
                "Werks-Kalibrierung ist vorausgefüllt. Übernehmen mit "
                "„Einrichten“ bzw. „Einstellungen aktualisieren“.")
    return (current, "",
            "Diese Einstellungen sind noch kein Profil – oben ein Profil "
            "wählen oder „Als neues Profil speichern…“ klicken.")


def _profile_section_lines(name, values):
    """Zeilen einer [profile:NAME]-Sektion (inkl. Kopfzeile)."""
    values = normalize_profile_values(values)
    return [f"[{PROFILE_PREFIX}{name}]"] + \
        [f"{key} = {values[key]}" for key in PROFILE_KEYS]


def _load_config_parser(path):
    """config.conf als ConfigParser lesen (fehlt die Datei → leerer Parser)."""
    import configparser

    cp = configparser.ConfigParser()
    cp.read(str(path), encoding="utf-8")
    return cp


def _write_config_parser(path, cp):
    """ConfigParser BOM-frei mit LF zurückschreiben (Kopf-Kommentar)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# DHL-Etikettensoftware – Konfiguration\n")
        cp.write(fh)


def _set_active_profile_in_parser(cp, name, values):
    """[crop] auf ein Profil setzen (Werte kopieren + profile = NAME)."""
    if not cp.has_section("crop"):
        cp.add_section("crop")
    for key in PROFILE_KEYS:
        cp["crop"][key] = values[key]
    cp["crop"]["profile"] = name


def set_active_profile(path, name):
    """Profil wechseln (auch ohne GUI): Werte des Profils nach [crop]
    kopieren und profile = NAME setzen. Der Watcher/Dienst übernimmt die
    Werte beim nächsten Neustart. ValueError bei unbekanntem Profil."""
    name = (name or "").strip()
    p = Path(path) if path else default_config_path()
    profiles, _active = read_profiles(str(p))
    if name not in profiles:
        known = ", ".join(profiles) or "(keine)"
        raise ValueError(f"Unbekanntes Profil: {name!r} (vorhanden: {known})")
    cp = _load_config_parser(p)
    _set_active_profile_in_parser(cp, name, profiles[name])
    _write_config_parser(p, cp)
    return profiles[name]


def upsert_profile(path, name, values, activate=False):
    """Profil anlegen/überschreiben; activate=True macht es zusätzlich zum
    aktiven Profil (Werte wandern nach [crop] – Dienst-Neustart nötig)."""
    name = (name or "").strip()
    if not valid_profile_name(name):
        raise ValueError(
            f"Unzulässiger Profilname: {name!r} (max. 40 Zeichen, ohne [ ] : =)")
    p = Path(path) if path else default_config_path()
    cp = _load_config_parser(p)
    section = PROFILE_PREFIX + name
    if not cp.has_section(section):
        cp.add_section(section)
    norm = normalize_profile_values(values)
    for key in PROFILE_KEYS:
        cp[section][key] = norm[key]
    if activate:
        _set_active_profile_in_parser(cp, name, norm)
    _write_config_parser(p, cp)
    return norm


def delete_profile(path, name):
    """Profil-Sektion aus der config.conf entfernen → True, wenn entfernt.
    War es das aktive Profil, wird [crop] profile geleert (die Werte selbst
    bleiben erhalten). Das Werks-Profil „Standard“ wird NICHT gelöscht."""
    name = (name or "").strip()
    if not name or name == FACTORY_PROFILE:
        return False
    p = Path(path) if path else default_config_path()
    if not p.exists():
        return False
    cp = _load_config_parser(p)
    removed = cp.remove_section(PROFILE_PREFIX + name)
    if removed and cp.has_section("crop"):
        if (cp["crop"].get("profile", "") or "").strip() == name:
            cp["crop"]["profile"] = ""
    if removed:
        _write_config_parser(p, cp)
    return removed


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
    if os.name == "nt":
        for modname, paket in (("pypdf", "pypdf"), ("pypdfium2", "pypdfium2"),
                               ("PIL", "Pillow"), ("win32print", "pywin32")):
            try:
                __import__(modname)
            except ImportError:
                problems.append(
                    f"Python-Paket fehlt: {paket}  (Installieren mit: "
                    f"pip install {paket})")
        return (len(problems) == 0, problems)
    if shutil.which("lpstat") is None:
        problems.append("CUPS-Druckdienst nicht gefunden (cups-client fehlt). "
                        "Bitte zuerst im Terminal ausführen:\n"
                        "  sudo apt install cups-client\nund dieses Setup neu starten.")
    if shutil.which("python3") is None:
        problems.append("Python 3 wurde nicht gefunden (python3).")
    return (len(problems) == 0, problems)


def write_config_file(path, *, printer, media, target_size_mm="100x150",
                      watch_mode="downloads", watch_dir="~/Downloads",
                      filename_pattern="versand|dhl|paket", side="top",
                      trim_top_mm=0.0, trim_bottom_mm=0.0,
                      trim_left_mm=0.0, trim_right_mm=0.0,
                      extra_options="", processed_dirname="gedruckt",
                      profile="", profiles=None):
    """Schreibt config.conf im selben Format wie install.sh (UTF-8 ohne BOM,
    LF-Zeilenenden). Wird von der Windows-GUI und der GTK-Kalibrierung genutzt.

    profile: aktives Profil → [crop] profile = NAME (leer = kein Profil).
    profiles: {Name: Werte} – wird als [profile:NAME]-Sektionen hinten
    angehängt (None = keine); die GUI übergibt hier immer den Bestand."""
    lines = [
        "# DHL-Etikettensoftware – Konfiguration",
        "# (Diese Datei verwaltet die Setup-GUI; manuelle Änderungen möglich.)",
        "",
        "[printer]",
        f"name = {printer}",
        f"media = {media}",
        f"extra_options = {extra_options}",
        "",
        "[crop]",
    ]
    if (profile or "").strip():
        lines.append(f"profile = {profile.strip()}")
    lines += [
        f"side = {side}",
        f"trim_top_mm = {trim_top_mm}",
        f"trim_bottom_mm = {trim_bottom_mm}",
        f"trim_left_mm = {trim_left_mm}",
        f"trim_right_mm = {trim_right_mm}",
        "page_index = 0",
        "use_ghostscript = false",
        f"target_size_mm = {target_size_mm}",
        "rotate = auto",
        "",
        "[watch]",
        f"mode = {watch_mode}",
        f"dir = {watch_dir}",
        f"filename_pattern = {filename_pattern}",
        f"processed_dirname = {processed_dirname}",
        "poll_seconds = 2.0",
        "process_existing = false",
    ]
    for name, values in (profiles or {}).items():
        name = (name or "").strip()
        if not valid_profile_name(name):
            continue
        lines.append("")
        lines += _profile_section_lines(name, values)
    lines.append("")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    return target


def read_installed_config(path=None):
    """Liest die installierte Konfiguration (für die GUI-Kalibrierung)."""
    import configparser
    p = Path(path) if path else default_config_path()
    cp = configparser.ConfigParser()
    cp.read(str(p), encoding="utf-8")

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
        "profile": get("crop", "profile"),
        "trim_top_mm": get("crop", "trim_top_mm", default="0"),
        "trim_bottom_mm": get("crop", "trim_bottom_mm", default="0"),
        "trim_left_mm": get("crop", "trim_left_mm", default="0"),
        "trim_right_mm": get("crop", "trim_right_mm", default="0"),
    }


def installed_state(path=None):
    """Ist die Software bereits installiert? → (installed, config | None).
    Installiert = config.conf vorhanden UND Druckername eingetragen."""
    p = Path(path) if path else default_config_path()
    if not p.exists():
        return False, None
    cfg = read_installed_config(str(p))
    return (bool(cfg.get("printer")), cfg)
