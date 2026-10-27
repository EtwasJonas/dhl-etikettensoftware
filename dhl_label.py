#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dhl_label.py â€“ DHL-Versandmarke aus A4-PDF croppen und auf einen
Thermoetikettendrucker (4x6 / 10x15) drucken.

Modi:
  watch                 Ãœberwacht den Watch-Ordner und druckt neue PDFs automatisch
  print DATEI           Druckt eine bestimmte PDF-Datei
  print-latest          Druckt die neueste passende PDF im Watch-Ordner (Desktop-Icon)
  crop IN [OUT]         Croppt nur (Test/Vorschau), ohne zu drucken
  calibrate             Interaktive Kalibrierungsdrucke
  show-config           Zeigt die effektive Konfiguration an

Konfiguration: ~/.config/dhl-label/config.conf
"""

import argparse
import configparser
import copy
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MM_TO_PT = 72.0 / 25.4

CONFIG_PATH = Path(
    os.environ.get("DHL_LABEL_CONFIG", "~/.config/dhl-label/config.conf")
).expanduser()


def log(msg):
    print(msg, flush=True)


class Config:
    """Liest config.conf und stellt Werte mit sinnvollen Defaults bereit."""

    def __init__(self, path=CONFIG_PATH):
        if not path.exists():
            raise SystemExit(
                f"Keine Konfiguration gefunden: {path}\n"
                "Bitte zuerst install.sh ausfÃ¼hren oder DHL_LABEL_CONFIG setzen."
            )
        cp = configparser.ConfigParser()
        cp.read(path, encoding="utf-8")

        p = cp["printer"] if cp.has_section("printer") else configparser.SectionProxy(cp, "printer")
        self.printer = p.get("name", fallback="")
        self.media = p.get("media", fallback="")
        self.lp_extra = p.get("extra_options", fallback="")

        c = cp["crop"] if cp.has_section("crop") else configparser.SectionProxy(cp, "crop")
        self.side = c.get("side", fallback="top").lower()          # top | bottom | full
        self.trim_top_mm = c.getfloat("trim_top_mm", fallback=0.0)
        self.trim_bottom_mm = c.getfloat("trim_bottom_mm", fallback=0.0)
        self.page_index = c.getint("page_index", fallback=0)       # 0 = erste Seite
        self.use_ghostscript = c.getboolean("use_ghostscript", fallback=False)
        self.target_mm = parse_size_mm(c.get("target_size_mm", fallback=""))
        self.rotate = c.get("rotate", fallback="auto").lower()     # auto | 0 | 90 | 270

        w = cp["watch"] if cp.has_section("watch") else configparser.SectionProxy(cp, "watch")
        self.watch_mode = w.get("mode", fallback="downloads").lower()  # downloads | custom
        self.watch_dir = Path(w.get("dir", fallback="~/Downloads")).expanduser()
        self.filename_pattern = w.get("filename_pattern", fallback="versand|dhl|paket")
        self.processed_dirname = w.get("processed_dirname", fallback="gedruckt")
        self.poll_seconds = w.getfloat("poll_seconds", fallback=2.0)
        self.process_existing = w.getboolean("process_existing", fallback=False)

    def __repr__(self):
        target = f"{self.target_mm[0]:g}x{self.target_mm[1]:g}mm" if self.target_mm else "aus (nur croppen)"
        return (
            f"printer={self.printer!r} media={self.media!r} lp_extra={self.lp_extra!r}\n"
            f"crop: side={self.side} trim_top={self.trim_top_mm}mm "
            f"trim_bottom={self.trim_bottom_mm}mm page={self.page_index} gs={self.use_ghostscript}\n"
            f"ziel: groesse={target} rotate={self.rotate}\n"
            f"watch: mode={self.watch_mode} dir={self.watch_dir} "
            f"pattern={self.filename_pattern!r} processed={self.processed_dirname!r}"
        )


def parse_size_mm(text):
    """Parst '100x150' (mm) zu (100.0, 150.0); leer/0 = None (nur croppen)."""
    text = (text or "").strip().lower().replace(",", ".").replace("\u00d7", "x")
    if not text or text in ("0", "none", "aus", "off"):
        return None
    m = re.match(r"^(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)$", text)
    if not m:
        raise SystemExit(
            f"Ung\u00fcltige Zielgr\u00f6\u00dfe: {text!r} \u2013 erwartet z.B. '100x150' "
            "(Breite x H\u00f6he in mm), oder leer, um nur zu croppen."
        )
    return (float(m.group(1)), float(m.group(2)))


# ---------------------------------------------------------------- Cropping

def _crop_region(page, cfg):
    """Berechnet die Crop-Region (in Punkten, absolut) fÃ¼r eine PDF-Seite."""
    box = page.mediabox
    W, H = float(box.width), float(box.height)
    left, bottom = float(box.left), float(box.bottom)

    if cfg.side == "top":
        y0, y1 = H / 2.0, H
    elif cfg.side == "bottom":
        y0, y1 = 0.0, H / 2.0
    else:  # full
        y0, y1 = 0.0, H

    y1 -= cfg.trim_top_mm * MM_TO_PT
    y0 += cfg.trim_bottom_mm * MM_TO_PT
    return left, bottom + y0, left + W, bottom + y1


def crop_pdf(src, dst, cfg):
    """Croppt die gewÃ¼nschte Region mit pypdf. Liefert (dst, Region) zurÃ¼ck."""
    from pypdf import PdfReader, PdfWriter  # lazy import
    from pypdf.generic import RectangleObject

    reader = PdfReader(str(src))
    writer = PdfWriter()
    page = reader.pages[cfg.page_index]
    region = _crop_region(page, cfg)
    page.cropbox = RectangleObject([float(v) for v in region])
    writer.add_page(page)
    with open(dst, "wb") as fh:
        writer.write(fh)
    return dst, region


def crop_with_ghostscript(src, dst, cfg):
    """Fallback: Hardcrop mit Ghostscript (falls pypdf-Ergebnis nicht passt)."""
    from pypdf import PdfReader  # nur zum Ausmessen

    page = PdfReader(str(src)).pages[cfg.page_index]
    box = page.mediabox
    W, H = float(box.width), float(box.height)

    if cfg.side == "top":
        y0, y1 = H / 2.0, H
    elif cfg.side == "bottom":
        y0, y1 = 0.0, H / 2.0
    else:
        y0, y1 = 0.0, H
    y1 -= cfg.trim_top_mm * MM_TO_PT
    y0 += cfg.trim_bottom_mm * MM_TO_PT

    height = y1 - y0
    # Inhalt nach unten schieben, sodass der gewÃ¼nschte Streifen am Seitenursprung liegt
    offset_y = -y0
    cmd = [
        "gs", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pdfwrite",
        "-dFIXEDMEDIA", "-dPDFFitPage",
        f"-dDEVICEWIDTHPOINTS={W:.2f}", f"-dDEVICEHEIGHTPOINTS={height:.2f}",
        "-c", f"<</PageOffset [0 {offset_y:.2f}]>> setpagedevice",
        "-sOutputFile", str(dst), "-f", str(src),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Ghostscript fehlgeschlagen:\n{proc.stderr}")
    return dst, (0, y0, W, y1)


def compose_target(src, dst, cfg, target_mm):
    """Croppt, dreht (falls nötig) und passt exakt auf die Ziel-Etikettengröße
    (z.B. 100x150 mm) ein: Inhalt proportional skaliert und zentriert.
    Ergebnis ist ein PDF, das exakt der Etikettengröße entspricht."""
    from pypdf import PdfReader, PdfWriter, Transformation  # lazy import
    from pypdf.generic import RectangleObject

    tw = target_mm[0] * MM_TO_PT
    th = target_mm[1] * MM_TO_PT

    reader = PdfReader(str(src))
    writer = PdfWriter()
    page = reader.pages[cfg.page_index]
    region = _crop_region(page, cfg)
    page.cropbox = RectangleObject([float(v) for v in region])
    writer.add_page(page)
    p = writer.pages[0]

    l, b, r, t = region
    w, h = r - l, t - b
    # Inhalt auf den Seitenursprung schieben (Boxen manuell nachziehen)
    p.add_transformation(Transformation().translate(-l, -b))
    p.mediabox = RectangleObject([0, 0, w, h])
    p.cropbox = RectangleObject([0, 0, w, h])

    # Drehung: auto = drehen, wenn Crop-Region und Ziel unterschiedliche
    # Orientierung haben (quer vs. hochkant)
    angle = 0
    if cfg.rotate == "auto":
        if (w > h) != (tw > th):
            angle = 90
    elif cfg.rotate in ("90", "270"):
        angle = int(cfg.rotate)
    if angle:
        p.rotation = angle
        p.transfer_rotation_to_content()
        box = p.mediabox
        w, h = float(box.width), float(box.height)

    # Proportional einpassen (kein Verzerren)
    s = min(tw / w, th / h)
    p.add_transformation(Transformation().scale(s, s))
    p.mediabox = RectangleObject([0, 0, w * s, h * s])
    p.cropbox = RectangleObject([0, 0, w * s, h * s])

    # Zentrieren auf der Zielseite
    tx = (tw - w * s) / 2.0
    ty = (th - h * s) / 2.0
    p.add_transformation(Transformation().translate(tx, ty))
    p.mediabox = RectangleObject([0, 0, tw, th])
    p.cropbox = RectangleObject([0, 0, tw, th])

    with open(dst, "wb") as fh:
        writer.write(fh)
    return dst, (0.0, 0.0, tw, th)


def make_cropped(src, dst, cfg, force_gs=False, **overrides):
    """Erzeugt die druckfertige PDF. Mit target_size_mm: exakt auf Etikettengröße
    eingepasst; sonst nur croppen (pypdf, optional Ghostscript-Fallback).
    overrides: temporäre Config-Überschreibungen, z.B. trim_top_mm=5.0."""
    if overrides:
        cfg = copy.copy(cfg)
        for key, value in overrides.items():
            setattr(cfg, key, value)
    target = getattr(cfg, "target_mm", None)
    if target and not isinstance(target, (tuple, list)):
        target = parse_size_mm(target)
    if target:
        return compose_target(src, dst, cfg, target)
    if cfg.use_ghostscript or force_gs:
        return crop_with_ghostscript(src, dst, cfg)
    return crop_pdf(src, dst, cfg)


# ---------------------------------------------------------------- Printing

def print_pdf(path, cfg):
    """Druckt eine (gecroppte) PDF via lp/CUPS. Gibt True bei Erfolg zurÃ¼ck."""
    cmd = ["lp", "-d", cfg.printer, "-o", f"media={cfg.media}"]
    if cfg.lp_extra.strip():
        cmd += shlex.split(cfg.lp_extra)
    cmd.append(str(path))
    log(f"Drucke: {' '.join(cmd)}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        log(f"lp nicht ausfÃ¼hrbar: {exc}")
        return False
    if proc.returncode != 0:
        log(f"lp-Fehler (rc={proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}")
        return False
    log(proc.stdout.strip())
    return True


def print_label(src, cfg, tmp_dir=None):
    """Croppt src und druckt das Ergebnis. Gibt True bei Erfolg zurÃ¼ck."""
    base = Path(src).stem + ".label.pdf"
    dst = Path(tmp_dir or tempfile.gettempdir()) / base
    try:
        dst, region = make_cropped(src, dst, cfg)
    except Exception as exc:
        log(f"Crop fehlgeschlagen fÃ¼r {src}: {exc}")
        return False
    ok = print_pdf(dst, cfg)
    try:
        dst.unlink()
    except OSError:
        pass
    return ok


# ---------------------------------------------------------------- Matching

def matches(path, cfg):
    """PrÃ¼ft, ob eine PDF gedruckt werden soll (Namensfilter im downloads-Modus)."""
    if path.suffix.lower() != ".pdf":
        return False
    if cfg.watch_mode == "downloads" and cfg.filename_pattern:
        if not re.search(cfg.filename_pattern, path.name, re.IGNORECASE):
            return False
    return True


def newest_matching(directory, cfg):
    pdfs = [p for p in Path(directory).glob("*.pdf") if matches(p, cfg)]
    if not pdfs:
        return None
    return max(pdfs, key=lambda p: p.stat().st_mtime)


# ---------------------------------------------------------------- Watcher

def watch(cfg, process_existing=False):
    directory = cfg.watch_dir
    if not directory.is_dir():
        raise SystemExit(f"Watch-Ordner existiert nicht: {directory}")
    processed_dir = directory / cfg.processed_dirname
    log(f"Ãœberwache {directory} (Modus: {cfg.watch_mode}, "
        f"Filter: {repr(cfg.filename_pattern) if cfg.watch_mode == 'downloads' else 'alle PDFs'})")

    pending = {}
    failures = {}
    MAX_RETRIES = 3
    known = set()
    if not (process_existing or cfg.process_existing):
        known = {p for p in directory.glob("*.pdf") if matches(p, cfg)}
        if known:
            log(f"Überspringe {len(known)} bereits vorhandene PDF(s) "
                "(--process-existing zum Nachdrucken)")

    while True:
        for pdf in directory.glob("*.pdf"):
            if pdf in known:
                continue
            if not matches(pdf, cfg):
                continue
            try:
                size = pdf.stat().st_size
            except FileNotFoundError:
                continue
            if size == 0:
                continue
            if pending.get(pdf) == size:
                # Größe stabil → Download abgeschlossen
                pending.pop(pdf, None)
                log(f"Neue PDF erkannt: {pdf.name}")
                if print_label(pdf, cfg):
                    failures.pop(pdf, None)
                    processed_dir.mkdir(exist_ok=True)
                    target = processed_dir / pdf.name
                    try:
                        pdf.replace(target)
                        log(f"Verschoben nach {target}")
                    except OSError as exc:
                        log(f"Konnte nicht verschieben: {exc}")
                else:
                    # Druckfehler (z.B. Drucker offline): begrenzt wiederholen,
                    # danach in fehlgeschlagen/ ablegen, damit der Loop nicht endlos spammt
                    attempts = failures.get(pdf, 0) + 1
                    failures[pdf] = attempts
                    if attempts >= MAX_RETRIES:
                        failed_dir = directory / "fehlgeschlagen"
                        failed_dir.mkdir(exist_ok=True)
                        try:
                            pdf.replace(failed_dir / pdf.name)
                            log(f"{pdf.name}: nach {attempts} Fehlversuchen nach "
                                "fehlgeschlagen/ verschoben – manuell nachdrucken "
                                "mit: dhl-label print")
                            failures.pop(pdf, None)
                        except OSError as exc:
                            log(f"Konnte nicht verschieben: {exc}")
                    else:
                        log(f"Druck fehlgeschlagen (Versuch {attempts}/{MAX_RETRIES}), "
                            "wird erneut versucht")
            else:
                pending[pdf] = size
        # Stale-Einträge räumen (Datei zwischendurch gelöscht)
        pending = {p: s for p, s in pending.items() if p.exists()}
        failures = {p: n for p, n in failures.items() if p.exists()}
        time.sleep(cfg.poll_seconds)


# ---------------------------------------------------------------- CLI-Modi

def cmd_watch(args, cfg):
    watch(cfg, process_existing=args.process_existing)


def cmd_print(args, cfg):
    ok = print_label(args.datei, cfg)
    sys.exit(0 if ok else 1)


def cmd_print_latest(args, cfg):
    src = newest_matching(args.ordner if args.ordner else cfg.watch_dir, cfg)
    if src is None:
        log("Keine passende PDF gefunden.")
        sys.exit(1)
    log(f"Neueste PDF: {src}")
    sys.exit(0 if print_label(src, cfg) else 1)


def cmd_crop(args, cfg):
    dst = args.out if args.out else "cropped.pdf"
    _, region = make_cropped(args.datei, dst, cfg, force_gs=args.ghostscript)
    if cfg.target_mm:
        log(f"Druckfertige Etiketten-PDF erzeugt: {dst} "
            f"({cfg.target_mm[0]:g} x {cfg.target_mm[1]:g} mm)")
    else:
        l, b, r, t = region
        log(f"Gecroppt nach {dst} (Region in pt: {l:.1f}, {b:.1f}, {r:.1f}, {t:.1f})")


def cmd_calibrate(args, cfg):
    """Druckt nacheinander Testvarianten (jeder Druck wird vorher bestätigt);
    der Nutzer beschriftet die Etiketten, um die beste Variante zu erkennen."""
    base = dict() if not cfg.target_mm else dict()
    variants = [
        ("Variante 1: obere Hälfte exakt (pypdf)", dict()),
        ("Variante 2: 5 mm oben abgeschnitten", dict(trim_top_mm=5.0)),
        ("Variante 3: 5 mm unten abgeschnitten", dict(trim_bottom_mm=5.0)),
        ("Variante 4: Ghostscript-Hardcrop (ohne Zielgröße)", dict(force_gs=True)),
        ("Variante 5: gedreht + exakt auf 100x150 mm eingepasst",
         dict(target_mm="100x150", rotate="auto")),
        ("Variante 6: gedreht + exakt auf 101,6x152,4 mm (4\"x6\") eingepasst",
         dict(target_mm="101.6x152.4", rotate="auto")),
    ]
    tmp = Path(tempfile.gettempdir()) / "dhl-label-calibrate"
    tmp.mkdir(exist_ok=True)
    # Referenz-PDF zum Testen beschaffen
    src = args.datei
    if not src:
        src = newest_matching(cfg.watch_dir, cfg)
    if not src or not Path(src).exists():
        raise SystemExit("Keine DHL-PDF gefunden. Aufruf: dhl-label calibrate PFAD/ZUR/PDF")
    src = Path(src)

    log(f"Kalibrierung mit: {src.name}")
    log("Es werden bis zu 6 Testdrucke vorgeschlagen – jeder Druck passiert "
        "nur nach deiner Bestätigung. Beschrifte jede Etikette, um die "
        "Variante zu identifizieren.\n")
    antwort = input("Testdrucke jetzt starten? (J/n): ")
    if antwort.strip().lower() in ("n", "nein"):
        log("Abgebrochen. Tipp: 'dhl-label crop DATEI.pdf' erzeugt eine "
            "Vorschau-PDF ganz ohne Druck.")
        return
    for i, (desc, kwargs) in enumerate(variants, 1):
        log(f"--- {desc} ---")
        eingabe = input("TESTDRUCK: Enter = drucken, s + Enter = überspringen, "
                        "q + Enter = abbrechen: ").strip().lower()
        if eingabe == "q":
            log("Abgebrochen.")
            break
        if eingabe == "s":
            log("Übersprungen.\n")
            continue
        out = tmp / f"variante{i}.pdf"
        try:
            make_cropped(src, out, cfg, **kwargs)
        except Exception as exc:
            log(f"Fehler bei {desc}: {exc}\n")
            continue
        print_pdf(out, cfg)
        log("Etikette beschriften (Variante merken)!\n")
    log("Fertig. Trage die Werte der besten Variante in die config.conf ein:")
    log(f"  {CONFIG_PATH}")
    log("  [crop] trim_top_mm / trim_bottom_mm  → Bereich eingrenzen")
    log("  [crop] target_size_mm (z.B. 100x150) → exakte Etikettengröße")
    log("  [crop] rotate (auto/90/270)          → falls die Marke verkehrt herum steht")
    log("Tipp: 'dhl-label crop DATEI.pdf' erzeugt ohne Druck eine Vorschau-PDF.")


def cmd_show_config(args, cfg):
    log(f"Konfigurationsdatei: {CONFIG_PATH}")
    log(cfg)


def cmd_printers(args, cfg):
    """Listet alle CUPS-Drucker (USB und WLAN/Netzwerk) mit Gerätetyp auf."""
    def run(cmd):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
            return proc.stdout.strip()
        except OSError as exc:
            raise SystemExit(f"{cmd[0]} nicht gefunden: {exc}")

    log("Drucker (Status):")
    log(run(["lpstat", "-p"]) or "(keine Drucker eingerichtet)")
    log("\nGeräte (Verbindungsart: usb:// = USB, ipp://|socket://|dnssd:// = WLAN/Netzwerk):")
    log(run(["lpstat", "-v"]) or "(keine Geräte)")
    log("\nStandarddrucker:")
    log(run(["lpstat", "-d"]))
    log("\nTipp: Drucker/Medium ändern in ~/.config/dhl-label/config.conf → [printer]")


def main():
    parser = argparse.ArgumentParser(
        prog="dhl-label",
        description="DHL-Versandmarke croppen und auf 4x6-Thermoetikettendrucker drucken.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    w = sub.add_parser("watch", help="Watch-Ordner überwachen")
    w.add_argument("--process-existing", action="store_true",
                   help="Beim Start auch bereits vorhandene PDFs drucken")
    w.set_defaults(func=cmd_watch)

    pr = sub.add_parser("print", help="Bestimmte PDF drucken")
    pr.add_argument("datei")
    pr.set_defaults(func=cmd_print)

    pl = sub.add_parser("print-latest", help="Neueste passende PDF drucken")
    pl.add_argument("ordner", nargs="?", default=None)
    pl.set_defaults(func=cmd_print_latest)

    cr = sub.add_parser("crop", help="Nur croppen (Vorschau)")
    cr.add_argument("datei")
    cr.add_argument("out", nargs="?", default=None)
    cr.add_argument("--ghostscript", action="store_true",
                    help="Ghostscript-Hardcrop statt pypdf")
    cr.set_defaults(func=cmd_crop)

    ca = sub.add_parser("calibrate", help="Kalibrierungsdrucke erzeugen")
    ca.add_argument("datei", nargs="?", default=None)
    ca.set_defaults(func=cmd_calibrate)

    sc = sub.add_parser("show-config", help="Konfiguration anzeigen")
    sc.set_defaults(func=cmd_show_config)

    pd = sub.add_parser("printers", help="CUPS-Drucker (USB/WLAN) auflisten")
    pd.set_defaults(func=cmd_printers)

    args = parser.parse_args()
    if args.command == "printers":
        args.func(args, None)  # funktioniert auch ohne config.conf
        return
    cfg = Config()
    args.func(args, cfg)


if __name__ == "__main__":
    main()

