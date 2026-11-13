# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build definition for berryMOTE.

Set BERRYMOTE_ONEFILE=0 for a folder build and BERRYMOTE_CONSOLE=1 for a
console/debug build. The wrapper in scripts/build.py sets these for you.
"""

import os
import sys


ROOT = os.path.abspath(SPECPATH)
PACKAGE = os.path.join(ROOT, "berryMOTE")
ONEFILE = os.environ.get("BERRYMOTE_ONEFILE", "1") != "0"
CONSOLE = os.environ.get("BERRYMOTE_CONSOLE", "0") == "1"

datas = [
    (os.path.join(PACKAGE, "templates"), "templates"),
    (os.path.join(PACKAGE, "static"), "static"),
    (os.path.join(PACKAGE, "berryTV.png"), "."),
]

for source, destination in (
    ("LICENSE", "."),
    ("THIRD_PARTY_NOTICES.md", "."),
    (os.path.join("LICENSES", "LGPL-3.0.txt"), "LICENSES"),
):
    path = os.path.join(ROOT, source)
    if os.path.exists(path):
        datas.append((path, destination))

hiddenimports = []
if sys.platform.startswith("win"):
    hiddenimports += ["pynput.keyboard._win32", "pynput.mouse._win32"]
elif sys.platform.startswith("linux"):
    hiddenimports += ["pynput.keyboard._xorg", "pynput.mouse._xorg"]
elif sys.platform == "darwin":
    hiddenimports += ["pynput.keyboard._darwin", "pynput.mouse._darwin"]

icon = os.path.join(PACKAGE, "berryLogo.ico") if sys.platform.startswith("win") else None

a = Analysis(
    [os.path.join(PACKAGE, "berryMOTE.py")],
    pathex=[PACKAGE],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="berryMOTE",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=CONSOLE,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="berryMOTE",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=CONSOLE,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="berryMOTE",
    )
