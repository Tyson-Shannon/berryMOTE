#!/usr/bin/env python3
"""Build a Linux AppImage from the PyInstaller onedir output."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
ONEDIR = DIST / "berryMOTE-onedir"
APPDIR = ROOT / "build" / "berryMOTE.AppDir"
ICON = ROOT / "berryMOTE" / "berryLogo.png"
DESKTOP = ROOT / "packaging" / "berryMOTE.desktop"
DEFAULT_OUTPUT = DIST / "berryMOTE-linux-x64.AppImage"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Wrap the berryMOTE onedir build in an AppImage.",
    )
    parser.add_argument(
        "--tool",
        default=os.environ.get("APPIMAGETOOL", "appimagetool"),
        help="path to appimagetool (default: $APPIMAGETOOL or PATH)",
    )
    parser.add_argument(
        "--arch",
        default=os.environ.get("ARCH", "x86_64"),
        help="AppImage architecture (default: x86_64)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"output path (default: {DEFAULT_OUTPUT.relative_to(ROOT)})",
    )
    return parser.parse_args()


def require_inputs() -> None:
    executable = ONEDIR / "berryMOTE"
    if not executable.is_file():
        raise SystemExit(
            f"{executable} was not found. Run: python scripts/build.py --onedir"
        )
    for path in (ICON, DESKTOP):
        if not path.is_file():
            raise SystemExit(f"Required file is missing: {path}")


def build_appdir() -> Path:
    if APPDIR.exists():
        shutil.rmtree(APPDIR)

    bin_dir = APPDIR / "usr" / "bin"
    bin_dir.mkdir(parents=True)
    shutil.copytree(ONEDIR, bin_dir, dirs_exist_ok=True)

    shutil.copy2(ICON, APPDIR / "berryMOTE.png")
    shutil.copy2(ICON, APPDIR / ".DirIcon")
    shutil.copy2(DESKTOP, APPDIR / "berryMOTE.desktop")

    icon_dir = APPDIR / "usr" / "share" / "icons" / "hicolor" / "512x512" / "apps"
    icon_dir.mkdir(parents=True)
    shutil.copy2(ICON, icon_dir / "berryMOTE.png")

    apps_dir = APPDIR / "usr" / "share" / "applications"
    apps_dir.mkdir(parents=True)
    shutil.copy2(DESKTOP, apps_dir / "berryMOTE.desktop")

    apprun = APPDIR / "AppRun"
    apprun.write_text(
        '#!/bin/sh\n'
        'HERE="$(dirname "$(readlink -f "$0")")"\n'
        'exec "$HERE/usr/bin/berryMOTE" "$@"\n',
        encoding="utf-8",
    )
    apprun.chmod(0o755)
    return APPDIR


def main() -> int:
    if not sys.platform.startswith("linux"):
        print("AppImage builds are only supported on Linux.", file=sys.stderr)
        return 1

    args = parse_args()
    require_inputs()
    appdir = build_appdir()

    env = os.environ.copy()
    env["ARCH"] = args.arch
    # appimagetool is commonly distributed as an AppImage itself. This lets it
    # run on systems without FUSE; native appimagetool builds ignore the flag.
    env.setdefault("APPIMAGE_EXTRACT_AND_RUN", "1")

    command = [
        str(args.tool),
        "--no-appstream",
        str(appdir),
        str(args.output),
    ]
    print("Running:", " ".join(command))
    result = subprocess.run(command, cwd=ROOT, env=env)
    if result.returncode != 0:
        return result.returncode

    if not args.output.is_file():
        print(f"Build finished but {args.output} was not created.", file=sys.stderr)
        return 1
    args.output.chmod(0o755)
    print(f"Built {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
