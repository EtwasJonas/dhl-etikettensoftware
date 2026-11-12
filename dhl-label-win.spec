# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller-Spec für die Windows-EXE (dhl-label.exe, onefile, windowed).

Aufbau:
  - dhl_label.py ist der Entry-Point; setup_gui_win.py (tkinter-GUI) und
    win_backend.py werden per hiddenimports eingebunden (dynamischer Import).
  - windowed (keine Konsole): GUI/Doppelklick-Nutzung; Log läuft in
    %LOCALAPPDATA%\dhl-label\dhl-label.log, printers/show-config zeigen
    Dialoge, wenn kein stdout existiert.
  - icon.ico wird für EXE- und Autostart-Verknüpfungs-Icon gebündelt.

Bauen:  python -m PyInstaller dhl-label-win.spec --noconfirm
Ergebnis: dist/dhl-label.exe
"""
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = [("icon.ico", "."), ("icon.png", "."), ("defaults.conf", ".")]
datas += collect_data_files("pypdfium2")

binaries = collect_dynamic_libs("pypdfium2")

hiddenimports = ["setup_gui_win", "win_backend"]
if sys.platform == "win32":
    hiddenimports += ["win32com.client", "pywintypes"]

a = Analysis(
    ["dhl_label.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="dhl-label",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon="icon.ico",
)
