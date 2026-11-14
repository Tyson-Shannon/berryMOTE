#!/usr/bin/env python3
"""Build a standalone berryMOTE executable with PyInstaller."""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "berryMOTE.spec"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package berryMOTE as a standalone executable.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--onefile",
        dest="onefile",
        action="store_true",
        help="create a single executable file (default)",
    )
    group.add_argument(
        "--onedir",
        dest="onefile",
        action="store_false",
        help="create an executable plus a support folder",
    )
    parser.add_argument(
        "--appimage",
        action="store_true",
        help="build a Linux AppImage (implies --onedir)",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="keep a console window for debugging",
    )
    parser.set_defaults(onefile=None)
    return parser.parse_args()


def built_path(onefile: bool) -> Path:
    executable = "berryMOTE.exe" if sys.platform.startswith("win") else "berryMOTE"
    if onefile:
        return ROOT / "dist" / executable
    return ROOT / "dist" / "berryMOTE-onedir" / executable


def main() -> int:
    args = parse_args()

    if args.appimage:
        if not sys.platform.startswith("linux"):
            print("--appimage is only supported on Linux.", file=sys.stderr)
            return 1
        if args.onefile is True:
            print("--appimage cannot be combined with --onefile.", file=sys.stderr)
            return 1
        args.onefile = False
    elif args.onefile is None:
        args.onefile = True

    if importlib.util.find_spec("PyInstaller") is None:
        print(
            "PyInstaller is not installed. Run: "
            "pip install -r requirements-dev.txt",
            file=sys.stderr,
        )
        return 1

    env = os.environ.copy()
    env["BERRYMOTE_ONEFILE"] = "1" if args.onefile else "0"
    env["BERRYMOTE_CONSOLE"] = "1" if args.console else "0"

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        str(SPEC),
    ]
    print("Running:", " ".join(command))
    result = subprocess.run(command, cwd=ROOT, env=env)
    if result.returncode != 0:
        return result.returncode

    target = built_path(args.onefile)
    if not target.exists():
        print(f"Build finished but {target} was not created.", file=sys.stderr)
        return 1

    print(f"Built {target}")

    if args.appimage:
        appimage_script = ROOT / "scripts" / "build_appimage.py"
        result = subprocess.run(
            [sys.executable, str(appimage_script)],
            cwd=ROOT,
            env=env,
        )
        if result.returncode != 0:
            return result.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
