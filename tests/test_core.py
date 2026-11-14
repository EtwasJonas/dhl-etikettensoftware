#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_core.py – Minimale Test-Suite (kein pytest nötig: python tests/test_core.py).

Plattformunabhängig (läuft unter Linux und Windows in CI):
  - Parser (Size, Trim-Zuschnitt, lpstat/lpoptions)
  - Config-Pfad-Auflösung + write_config_file (BOM-frei, LF)
  - Crop-/Compose-Geometrie auf synthetischem A4-Test-PDF:
    Zielseite exakt 100x150 mm, Uniform-Scale-Assert (|a|==|d|, |b|==|c|)
    aus dem Output-Contentstream + Ecken-Check (docs/architektur.md §8.3)
  - Watcher-Namensfilter
  - fit_rect (Windows-Rasterdruck): Uniform-Scale in den druckbaren Bereich
Windows-zusätzlich (nur ausgeführt, wenn pywin32 vorhanden):
  - Drucker-Auflistung / Papierformate via Windows-Druck-API
"""

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import gui_helpers as gh  # noqa: E402
from gui_helpers import default_config_path  # noqa: E402

MM_TO_PT = 72.0 / 25.4
TARGET_100x150 = (100.0 * MM_TO_PT, 150.0 * MM_TO_PT)  # 283.46 x 425.20 pt

try:
    import pypdf  # noqa: F401
    HAVE_PYPDF = True
except ImportError:
    HAVE_PYPDF = False


# ------------------------------------------------------------------ Parser

def test_parse_size_mm():
    assert gh.parse_size_mm("100x150") == (100.0, 150.0)
    assert gh.parse_size_mm("101,6x152,4") == (101.6, 152.4)
    assert gh.parse_size_mm(" 100 × 150 ") == (100.0, 150.0)
    assert gh.parse_size_mm("") is None
    assert gh.parse_size_mm("0") is None
    assert gh.parse_size_mm("aus") is None
    for bad in ("abc", "100", "100x", "x150", "100x150x10"):
        try:
            gh.parse_size_mm(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"parse_size_mm({bad!r}) sollte ValueError werfen")


def test_parse_printers():
    out = ("printer Vretti is idle.  enabled since Jan 01 00:00\n"
           "printer HP is disabled.  enabled since Jan 01\n"
           "printer LaserPJ is idle.\n"
           "random line\n")
    printers = gh.parse_printers(out)
    assert ("Vretti", "is idle.  enabled since Jan 01 00:00") in printers, printers
    assert ("HP", "is disabled.  enabled since Jan 01") in printers, printers
    assert ("LaserPJ", "is idle") in printers, printers
    assert len(printers) == 3


def test_parse_media():
    raw = "PageSize/Page Size: 4x6 100x150 *Letter A4"
    sizes, default, raw_line = gh.parse_media(raw)
    assert sizes == ["4x6", "100x150", "Letter", "A4"], sizes
    assert default == "Letter"
    assert raw_line == raw
    assert gh.parse_media("keine passende zeile") is None
    sizes, default, _raw = gh.parse_media("media: *4x6 100x150")
    assert sizes == ["4x6", "100x150"] and default == "4x6"


def test_parse_trim_mm():
    """Zuschnitt-Eingaben: Komma erlaubt, leer = 0, Negativ/Unsinn abgelehnt."""
    assert gh.parse_trim_mm("") == 0.0
    assert gh.parse_trim_mm("0") == 0.0
    assert gh.parse_trim_mm(" 5 ") == 5.0
    assert gh.parse_trim_mm("16,24") == 16.24
    assert gh.parse_trim_mm("3.08") == 3.08
    for bad in ("abc", "-1", "nan", "inf", "1x2"):
        try:
            gh.parse_trim_mm(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"parse_trim_mm({bad!r}) sollte ValueError werfen")


def test_build_install_cmd_with_trims():
    """install.sh-Flags enthalten die Zuschnitt-Werte (GUI → Installer)."""
    cmd = gh.build_install_cmd(
        "install.sh", printer="Vretti", media="4x6", target="101.6x152.4",
        watch_mode="downloads", watch_dir="/home/u/Downloads",
        pattern="versand|dhl|paket", side="top",
        trim_top=16.24, trim_bottom=16.66, trim_left=3.08, trim_right=4.13)
    expected = ["--trim-top", "16.24", "--trim-bottom", "16.66",
                "--trim-left", "3.08", "--trim-right", "4.13"]
    start = cmd.index("--trim-top")
    assert cmd[start:start + 8] == expected, cmd
    assert "--non-interactive" in cmd and "--pkexec" in cmd
    # Default: alle vier Zuschnitt-Flags vorhanden (0, keine Lücken)
    default = gh.build_install_cmd(
        "install.sh", printer="V", media="M", target="100x150",
        watch_mode="downloads", watch_dir="/home/u/Downloads",
        pattern="p", side="top")
    assert default[default.index("--trim-top"):default.index("--trim-top") + 8] == \
        ["--trim-top", "0", "--trim-bottom", "0",
         "--trim-left", "0", "--trim-right", "0"]


def test_calibration_variants_and_cmds():
    variants = gh.calibration_variants()
    assert len(variants) == 6
    cmd = gh.build_crop_cmd("python3", "dhl_label.py", "in.pdf", "out.pdf",
                            ["--gs", "--target", ""])
    assert cmd[:5] == ["python3", "dhl_label.py", "crop", "in.pdf", "out.pdf"]
    assert "--gs" in cmd and "--target" in cmd
    lp = gh.build_print_cmd("Vretti", "4x6", "x.pdf", "-o landscape")
    assert lp == ["lp", "-d", "Vretti", "-o", "media=4x6", "-o", "landscape", "x.pdf"]
    assert gh.build_print_cmd("V", "", "x.pdf") == ["lp", "-d", "V", "-o", "media=", "x.pdf"]


# ------------------------------------------------------------------ Config

def test_default_config_path_env_override():
    with tempfile.TemporaryDirectory() as tmp:
        custom = str(Path(tmp) / "custom.conf")
        old = os.environ.get("DHL_LABEL_CONFIG")
        try:
            os.environ["DHL_LABEL_CONFIG"] = custom
            assert default_config_path() == Path(custom)
            assert gh.default_config_path() == Path(custom)
        finally:
            if old is None:
                os.environ.pop("DHL_LABEL_CONFIG", None)
            else:
                os.environ["DHL_LABEL_CONFIG"] = old


def test_default_config_path_platform():
    old = os.environ.pop("DHL_LABEL_CONFIG", None)
    try:
        path = default_config_path()
        if os.name == "nt":
            assert "dhl-label" in str(path) and str(path).endswith("config.conf")
            assert "AppData" in str(path) or str(path).startswith(str(Path.home()))
        else:
            # expanduser: echtes Home-Verzeichnis (wie der alte CONFIG_PATH-Code)
            s = str(path)
            assert s.endswith(".config/dhl-label/config.conf"), s
            assert not s.startswith("~"), f"~ sollte expandiert sein: {s}"
            assert Path(s).is_absolute(), s
    finally:
        if old is not None:
            os.environ["DHL_LABEL_CONFIG"] = old


def test_write_config_file_roundtrip():
    import dhl_label

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "dhl-label" / "config.conf"
        gh.write_config_file(
            path, printer="Vretti USB", media="User Defined 100x150mm",
            target_size_mm="100x150", watch_mode="downloads",
            watch_dir=str(Path(tmp) / "Downloads"),
            filename_pattern="versand|dhl|paket", side="top",
            trim_top_mm=5.0, trim_bottom_mm=2.5,
            trim_left_mm=3.04, trim_right_mm=4.04)
        data = path.read_bytes()
        assert not data.startswith(b"\xef\xbb\xbf"), "config.conf darf kein BOM haben"
        assert b"\r" not in data, "config.conf muss LF-Zeilenenden haben"
        cfg = dhl_label.Config(path)
        assert cfg.printer == "Vretti USB"
        assert cfg.media == "User Defined 100x150mm"
        assert cfg.side == "top"
        assert cfg.trim_top_mm == 5.0
        assert cfg.trim_bottom_mm == 2.5
        assert cfg.trim_left_mm == 3.04
        assert cfg.trim_right_mm == 4.04
        assert cfg.target_mm == (100.0, 150.0)
        assert cfg.watch_mode == "downloads"
        assert cfg.rotate == "auto"
        assert cfg.page_index == 0


def test_config_env_override_used_by_dhl_label():
    import dhl_label

    with tempfile.TemporaryDirectory() as tmp:
        conf = Path(tmp) / "env.conf"
        gh.write_config_file(conf, printer="X", media="M")
        old = os.environ.get("DHL_LABEL_CONFIG")
        try:
            os.environ["DHL_LABEL_CONFIG"] = str(conf)
            import importlib
            importlib.reload(dhl_label)
            assert dhl_label.CONFIG_PATH == conf
        finally:
            if old is None:
                os.environ.pop("DHL_LABEL_CONFIG", None)
            else:
                os.environ["DHL_LABEL_CONFIG"] = old
        importlib.reload(dhl_label)  # sauberer Zustand für weitere Tests


# ------------------------------------------------------------------ Watcher

def test_matches_filter():
    import dhl_label

    cfg = SimpleNamespace(watch_mode="downloads",
                          filename_pattern="versand|dhl|paket")
    assert dhl_label.matches(Path("dhl-versand-1234.pdf"), cfg)
    assert dhl_label.matches(Path("Paketschein.PDF"), cfg)
    assert not dhl_label.matches(Path("urlaub.pdf"), cfg)
    assert not dhl_label.matches(Path("dhl-versand.docx"), cfg)
    custom = SimpleNamespace(watch_mode="custom", filename_pattern="")
    assert dhl_label.matches(Path("irgendwas.pdf"), custom)
    assert not dhl_label.matches(Path("irgendwas.txt"), custom)


# ------------------------------------------------------------------ Crop/Compose

def _write_test_a4(path):
    """A4-PDF mit echtem Inhalt: Rechteck in der oberen Hälfte, Rest unten."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject

    writer = PdfWriter()
    writer.add_blank_page(width=595.28, height=841.89)
    stream = DecodedStreamObject()
    stream.set_data(b"0 0 1 rg 100 500 200 100 re f\n"
                    b"0 1 0 rg 100 100 100 80 re f\n")
    writer.pages[0].replace_contents(stream)
    with open(path, "wb") as fh:
        writer.write(fh)
    return PdfReader(str(path))


def test_crop_pdf_top_half():
    import dhl_label

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "a4.pdf"
        _write_test_a4(src)
        cfg = SimpleNamespace(side="top", trim_top_mm=0.0, trim_bottom_mm=0.0,
                              trim_left_mm=0.0, trim_right_mm=0.0,
                              page_index=0, use_ghostscript=False)
        dst = Path(tmp) / "crop.pdf"
        _, region = dhl_label.crop_pdf(src, dst, cfg)
        l, b, r, t = region
        assert abs(r - l - 595.28) < 0.5
        assert abs(t - b - 841.89 / 2) < 0.5  # obere Hälfte
        assert abs(b - 841.89 / 2) < 0.5


def test_load_defaults_shipped():
    """Die Werks-Kalibrierung (defaults.conf) muss ausgeliefert werden und
    die am SN 420B verifizierten Werte enthalten."""
    defaults = gh.load_defaults()
    assert defaults, "defaults.conf fehlt oder ist unlesbar"
    assert defaults["side"] == "top"
    assert defaults["target_size_mm"] == "101.6x152.4"
    assert defaults["rotate"] == "auto"
    assert float(defaults["trim_top_mm"]) == 16.24
    assert float(defaults["trim_bottom_mm"]) == 16.66
    assert float(defaults["trim_left_mm"]) == 3.08
    assert float(defaults["trim_right_mm"]) == 4.13


def test_defaults_file_bom_free_lf():
    path = REPO / "defaults.conf"
    assert path.exists(), "defaults.conf fehlt im Repo"
    data = path.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf"), "defaults.conf darf kein BOM haben"
    assert b"\r" not in data, "defaults.conf muss LF-Zeilenenden haben"


def test_crop_region_with_x_trims():
    """trim_left/right verschieben/begrenzen die Crop-Region in x-Richtung."""
    import dhl_label

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "a4.pdf"
        _write_test_a4(src)
        cfg = SimpleNamespace(side="top", trim_top_mm=0.0, trim_bottom_mm=0.0,
                              trim_left_mm=10.0, trim_right_mm=20.0,
                              page_index=0, use_ghostscript=False)
        dst = Path(tmp) / "crop_trims.pdf"
        _, region = dhl_label.crop_pdf(src, dst, cfg)
        l, b, r, t = region
        assert abs(l - 10.0 * MM_TO_PT) < 0.5, f"links {l} != {10.0 * MM_TO_PT}"
        assert abs(r - (595.28 - 20.0 * MM_TO_PT)) < 0.5, f"rechts {r}"
        # y unverändert (obere Hälfte)
        assert abs(b - 841.89 / 2) < 0.5


def _collect_cm_matrices(page, reader):
    """Alle cm-Operatoren des Contentstreams, in Stream-Reihenfolge."""
    from pypdf.generic import ContentStream

    stream = ContentStream(page.get_contents(), reader)
    matrices = []
    for operands, operator in stream.operations:
        if operator == b"cm":
            matrices.append([float(v) for v in operands])
    assert matrices, "Contentstream enthält keine cm-Operationen"
    return matrices


def _point_matrix(matrices):
    """Baut die effektive Punkt-Abbildungsmatrix aus den cm-Operatoren.

    PDF nutzt Row-Vektoren ([x y 1] · M): der **letzte** Stream-Operator
    wirkt zuerst auf den Punkt, der erste zuletzt. pypdf prependet jede
    add_transformation vor den Content – die Stream-Reihenfolge ist also
    die umgekehrte Aufruf-Reihenfolge. Richtig: Stream rückwärts
    komponieren, erster Operator wirkt zuerst (docs/architektur.md §8.3).
    """
    ctm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    for matrix in reversed(matrices):
        ctm = _compose(ctm, matrix)
    return ctm


def _compose(m_first, m_then):
    """Zusammensetzen: m_first zuerst, dann m_then (Punkt-Mapping-Reihenfolge)."""
    a1, b1, c1, d1, e1, f1 = m_first
    a2, b2, c2, d2, e2, f2 = m_then
    return [a2 * a1 + c2 * b1,
            b2 * a1 + d2 * b1,
            a2 * c1 + c2 * d1,
            b2 * c1 + d2 * d1,
            a2 * e1 + c2 * f1 + e2,
            b2 * e1 + d2 * f1 + f2]


def _apply(m, x, y):
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


def _assert_uniform(matrix, context):
    a, b, c, d, _e, _f = matrix
    assert abs(abs(a) - abs(d)) < 1e-6, \
        f"Uniform-Scale verletzt ({context}): a={a}, d={d}"
    assert abs(abs(b) - abs(c)) < 1e-6, \
        f"Uniform-Scale verletzt ({context}): b={b}, c={c}"
    # Skalierungsfaktor gleich auf beiden Achsen (Rotation: a=d=0, b=-c)
    if abs(a) > 1e-9:
        assert abs(abs(a) - abs(d)) < 1e-6
        assert abs(b) < 1e-9 and abs(c) < 1e-9, \
            f"Nicht uniform skaliert ({context}): a={a}, b={b}, c={c}, d={d}"
    else:  # 90°-Rotation
        assert abs(a) < 1e-9 and abs(d) < 1e-9
        assert abs(abs(b) - abs(c)) < 1e-6


def test_compose_target_uniform_scale_and_corners():
    import dhl_label

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "a4.pdf"
        _write_test_a4(src)
        cfg = SimpleNamespace(side="top", trim_top_mm=0.0, trim_bottom_mm=0.0,
                              trim_left_mm=0.0, trim_right_mm=0.0,
                              page_index=0, rotate="auto", use_ghostscript=False)
        dst = Path(tmp) / "composed.pdf"
        _, region = dhl_label.compose_target(src, dst, cfg, (100.0, 150.0))

        from pypdf import PdfReader
        reader = PdfReader(str(dst))
        page = reader.pages[0]
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        assert abs(w - TARGET_100x150[0]) < 0.05, f"Zielbreite {w} != {TARGET_100x150[0]}"
        assert abs(h - TARGET_100x150[1]) < 0.05, f"Zielhöhe {h} != {TARGET_100x150[1]}"

        ctm = _point_matrix(_collect_cm_matrices(page, reader))
        _assert_uniform(ctm, "effektive CTM")

        # Marke (100,500)-(300,600) muss komplett auf der Zielseite landen,
        # unten liegender Inhalt (100,100)-(200,180) ist außerhalb (weggeschnitten)
        for x, y in ((100, 500), (300, 500), (100, 600), (300, 600)):
            px, py = _apply(ctm, x, y)
            assert -0.5 <= px <= TARGET_100x150[0] + 0.5, (x, y, px, py)
            assert -0.5 <= py <= TARGET_100x150[1] + 0.5, (x, y, px, py)


def test_compose_target_rot270_still_uniform():
    """rotate=270 (falls Marke verkehrt herum): ebenfalls keine Verzerrung."""
    import dhl_label

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "a4.pdf"
        _write_test_a4(src)
        cfg = SimpleNamespace(side="top", trim_top_mm=0.0, trim_bottom_mm=0.0,
                              trim_left_mm=0.0, trim_right_mm=0.0,
                              page_index=0, rotate="270", use_ghostscript=False)
        dst = Path(tmp) / "composed270.pdf"
        dhl_label.compose_target(src, dst, cfg, (100.0, 150.0))
        from pypdf import PdfReader
        reader = PdfReader(str(dst))
        page = reader.pages[0]
        assert abs(float(page.mediabox.width) - TARGET_100x150[0]) < 0.05
        ctm = _point_matrix(_collect_cm_matrices(page, reader))
        _assert_uniform(ctm, "rotate=270")


# ------------------------------------------------------------------ Profile

def test_valid_profile_name():
    assert gh.valid_profile_name("Standard")
    assert gh.valid_profile_name("Mein Drucker")
    assert gh.valid_profile_name("Test 2")
    for bad in ("", "   ", "x" * 41, "a:b", "a[b]", "a=b", "a\tb"):
        assert not gh.valid_profile_name(bad), bad


def test_normalize_profile_values():
    values = gh.normalize_profile_values({
        "trim_top_mm": "16,24", "trim_bottom_mm": "16.66",
    })
    assert values["trim_top_mm"] == "16.24"
    assert values["trim_bottom_mm"] == "16.66"
    assert values["trim_left_mm"] == "0"
    assert values["side"] == "top"        # fehlend → Default
    assert values["rotate"] == "auto"     # fehlend → Default
    assert values["target_size_mm"] == ""  # fehlend → leer (= nur croppen)


def test_profile_values_equal():
    factory = gh.factory_profile_values()
    assert factory, "defaults.conf muss lesbar sein"
    assert gh.profile_values_equal(factory, dict(factory))
    assert gh.profile_values_equal(factory, {**factory, "trim_top_mm": "16,24"})
    assert not gh.profile_values_equal(factory, {**factory, "trim_top_mm": "17"})
    assert not gh.profile_values_equal(factory, {**factory, "side": "bottom"})
    assert gh.profile_values_equal({"target_size_mm": ""},
                                   {"target_size_mm": "0"})


def test_write_config_file_with_profiles_roundtrip():
    import configparser
    import dhl_label

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.conf"
        profiles = {
            "Standard": gh.normalize_profile_values(gh.load_defaults()),
            "Test": {"side": "top", "trim_top_mm": "5", "trim_bottom_mm": "5",
                     "trim_left_mm": "0", "trim_right_mm": "0",
                     "target_size_mm": "100x150", "rotate": "auto"},
        }
        gh.write_config_file(
            path, printer="Vretti", media="4x6", target_size_mm="101.6x152.4",
            watch_mode="downloads", watch_dir=str(tmp),
            filename_pattern="versand|dhl|paket", side="top",
            trim_top_mm=16.24, trim_bottom_mm=16.66, trim_left_mm=3.08,
            trim_right_mm=4.13, profile="Test", profiles=profiles)
        data = path.read_bytes()
        assert not data.startswith(b"\xef\xbb\xbf"), "kein BOM erlaubt"
        assert b"\r" not in data, "LF-Zeilenenden"
        cp = configparser.ConfigParser()
        cp.read(str(path), encoding="utf-8")
        assert cp["crop"]["profile"] == "Test"
        assert cp["profile:Test"]["trim_top_mm"] == "5"
        assert cp["profile:Standard"]["trim_top_mm"] == "16.24"
        cfg = dhl_label.Config(path)
        assert cfg.profile == "Test"
        assert cfg.trim_top_mm == 16.24
        assert cfg.target_mm == (101.6, 152.4)


def test_read_profiles_legacy_config_gets_factory_standard():
    """Alte config.conf (vor v1.2.0, Zuschnitt überall 0, kein Profil):
    GUI-Vorbefüllung muss die Werks-Kalibrierung zeigen (Zweit-PC-Fix)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.conf"
        gh.write_config_file(path, printer="Vretti", media="4x6",
                             target_size_mm="100x150", watch_dir=str(tmp))
        profiles, active = gh.read_profiles(path)
        assert "Standard" in profiles
        assert active == ""
        factory = gh.factory_profile_values()
        assert float(profiles["Standard"]["trim_top_mm"]) == \
            float(factory["trim_top_mm"])
        cfg = gh.read_installed_config(path)
        values, selected, hinweis = gh.resolve_startup_values(cfg, profiles, active)
        assert selected == "Standard"
        assert float(values["trim_top_mm"]) == float(factory["trim_top_mm"])
        assert hinweis, "Migration muss als Hinweis sichtbar sein"


def test_resolve_startup_values():
    profiles = {
        "Standard": gh.normalize_profile_values(gh.load_defaults()),
        "Test": gh.normalize_profile_values({
            "side": "top", "trim_top_mm": "5", "trim_bottom_mm": "5",
            "trim_left_mm": "0", "trim_right_mm": "0",
            "target_size_mm": "100x150", "rotate": "auto"}),
    }
    # 1) Aktives Profil gewinnt
    test_values = profiles["Test"]
    values, selected, hinweis = gh.resolve_startup_values(
        test_values, profiles, "Test")
    assert selected == "Test" and hinweis is None
    assert values["trim_top_mm"] == "5"
    # 2) Kein Profil, aber Werte == Werks-Standard → Standard gewählt
    values, selected, hinweis = gh.resolve_startup_values(
        gh.normalize_profile_values(gh.load_defaults()), profiles, "")
    assert selected == "Standard" and hinweis is None
    # 3) Eigene Werte, kein Profil → leere Auswahl + Hinweis
    custom = dict(test_values, trim_top_mm="7")
    values, selected, hinweis = gh.resolve_startup_values(custom, profiles, "")
    assert selected == "" and hinweis
    assert values["trim_top_mm"] == "7"


def test_upsert_set_active_delete_profile():
    import configparser
    import dhl_label

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.conf"
        gh.write_config_file(path, printer="Vretti", media="4x6",
                             target_size_mm="101.6x152.4", watch_dir=str(tmp))
        values = {"side": "top", "trim_top_mm": 5, "trim_bottom_mm": 5,
                  "trim_left_mm": 0, "trim_right_mm": 0,
                  "target_size_mm": "100x150", "rotate": "auto"}
        gh.upsert_profile(path, "Test", values, activate=True)
        cp = configparser.ConfigParser()
        cp.read(str(path), encoding="utf-8")
        assert cp["profile:Test"]["trim_top_mm"] == "5"
        assert cp["crop"]["profile"] == "Test"
        assert float(cp["crop"]["trim_top_mm"]) == 5.0
        cfg = dhl_label.Config(path)
        assert cfg.profile == "Test" and cfg.trim_top_mm == 5.0
        # Wechsel: Werks-Profil → Werte wandern nach [crop]
        factory = gh.factory_profile_values()
        gh.set_active_profile(path, "Standard")
        cfg = dhl_label.Config(path)
        assert cfg.profile == "Standard"
        assert cfg.trim_top_mm == float(factory["trim_top_mm"])
        # Löschen: Standard geschützt; Test (nicht mehr aktiv) verschwindet,
        # der Profil-Marker bleibt auf dem aktiven Profil
        assert not gh.delete_profile(path, "Standard")
        assert gh.delete_profile(path, "Test")
        cp = configparser.ConfigParser()
        cp.read(str(path), encoding="utf-8")
        assert not cp.has_section("profile:Test")
        assert cp["crop"]["profile"] == "Standard"
        assert cp["printer"]["name"] == "Vretti"
        assert float(cp["crop"]["trim_top_mm"]) == float(factory["trim_top_mm"])
        # Löschen des AKTIVEN Profils leert den Marker ([crop]-Werte bleiben)
        gh.upsert_profile(path, "Aktiv", values, activate=True)
        assert gh.delete_profile(path, "Aktiv")
        cp = configparser.ConfigParser()
        cp.read(str(path), encoding="utf-8")
        assert not cp.has_section("profile:Aktiv")
        assert cp["crop"]["profile"] == ""
        assert cp["printer"]["name"] == "Vretti"
        assert float(cp["crop"]["trim_top_mm"]) == 5.0


def test_build_install_cmd_with_profile():
    cmd = gh.build_install_cmd(
        "install.sh", printer="V", media="M", target="100x150",
        watch_mode="downloads", watch_dir="/d", pattern="p", side="top",
        profile="Zweit-PC")
    start = cmd.index("--profile")
    assert cmd[start:start + 2] == ["--profile", "Zweit-PC"]
    no_profile = gh.build_install_cmd(
        "install.sh", printer="V", media="M", target="100x150",
        watch_mode="downloads", watch_dir="/d", pattern="p", side="top")
    assert "--profile" not in no_profile


# ------------------------------------------------------------------ Windows

def test_fit_rect_uniform():
    from win_backend import fit_rect

    img_w, img_h = TARGET_100x150  # pt ≈ Seitenverhältnis 100x150
    area_w, area_h = 2000, 3000
    x, y, w, h = fit_rect(img_w, img_h, area_w, area_h)
    assert abs(w / h - img_w / img_h) < 1e-9, "fit_rect muss das Seitenverhältnis erhalten"
    assert w <= area_w + 1e-9 and h <= area_h + 1e-9
    assert abs(x - (area_w - w) / 2) < 1e-9 and abs(y - (area_h - h) / 2) < 1e-9
    # Extremfall: viel breiteres Bild
    x, y, w, h = fit_rect(4000, 1000, 1000, 1000)
    assert abs(w / h - 4.0) < 1e-9


def test_paper_match():
    from win_backend import _match_paper_id

    papers = [(1, "Letter"), (2, "A4"), (5, "User Defined 100x150mm"),
              (9, "4x6in"), (12, "User Defined 101.6x152.4mm")]
    assert _match_paper_id(papers, "User Defined 100x150mm") == 5
    assert _match_paper_id(papers, "100x150") == 5
    assert _match_paper_id(papers, "4x6") == 9
    assert _match_paper_id(papers, "101.6x152.4") == 12
    assert _match_paper_id(papers, "unbekannt") is None
    assert _match_paper_id(papers, "") is None


def test_windows_printer_api():
    """Nur unter Windows (CI windows-latest / lokale Windows-Tests)."""
    if os.name != "nt":
        return
    try:
        import win32print  # noqa: F401
    except ImportError:
        print("  (pywin32 nicht verfügbar – Windows-API-Tests übersprungen)")
        return
    printers = win_backend_probe()
    print(f"  Windows-Drucker gefunden: {printers}")


def win_backend_probe():
    from win_backend import list_printers, paper_sizes

    printers = list_printers()
    assert isinstance(printers, list)
    for name, status in printers:
        assert isinstance(name, str) and name
        assert isinstance(status, str)
        papers, default_id = paper_sizes(name)
        assert isinstance(papers, list)
        assert default_id is None or isinstance(default_id, int)
    return [name for name, _status in printers]


# ------------------------------------------------------------------ Runner

TESTS = [
    test_parse_size_mm,
    test_parse_printers,
    test_parse_media,
    test_parse_trim_mm,
    test_build_install_cmd_with_trims,
    test_calibration_variants_and_cmds,
    test_default_config_path_env_override,
    test_default_config_path_platform,
    test_load_defaults_shipped,
    test_defaults_file_bom_free_lf,
    test_write_config_file_roundtrip,
    test_config_env_override_used_by_dhl_label,
    test_valid_profile_name,
    test_normalize_profile_values,
    test_profile_values_equal,
    test_write_config_file_with_profiles_roundtrip,
    test_read_profiles_legacy_config_gets_factory_standard,
    test_resolve_startup_values,
    test_upsert_set_active_delete_profile,
    test_build_install_cmd_with_profile,
    test_matches_filter,
    test_crop_pdf_top_half,
    test_crop_region_with_x_trims,
    test_compose_target_uniform_scale_and_corners,
    test_compose_target_rot270_still_uniform,
    test_fit_rect_uniform,
    test_paper_match,
    test_windows_printer_api,
]


def main():
    failures = []
    if not HAVE_PYPDF:
        print("HINWEIS: pypdf nicht installiert – PDF-Tests werden übersprungen.")
    for test in TESTS:
        if test is test_windows_printer_api and os.name != "nt":
            continue
        label = test.__name__
        try:
            if test in (test_crop_pdf_top_half,
                        test_compose_target_uniform_scale_and_corners,
                        test_compose_target_rot270_still_uniform) and not HAVE_PYPDF:
                print(f"SKIP {label} (pypdf fehlt)")
                continue
            test()
            print(f"OK   {label}")
        except Exception as exc:
            failures.append((label, exc))
            print(f"FAIL {label}: {exc!r}")
    print()
    if failures:
        print(f"{len(failures)} Test(s) fehlgeschlagen.")
        sys.exit(1)
    print(f"Alle {len(TESTS)} Tests bestanden.")


if __name__ == "__main__":
    main()
