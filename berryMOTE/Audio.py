"""Volume control helpers for berryMOTE.

Using the system mixer is more reliable than injecting media keys, especially
on Wayland where key handling is compositor-specific.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Optional


class AudioController:
    def __init__(self) -> None:
        self.backend: Optional[str] = None
        self.last_error = ""
        self._detect()

    def _detect(self) -> None:
        if not sys.platform.startswith("linux"):
            return

        candidates = [
            ("wpctl", self._probe_wpctl),
            ("pactl", self._probe_pactl),
            ("amixer", self._probe_amixer),
        ]
        for name, probe in candidates:
            if shutil.which(name) and probe():
                self.backend = name
                return

    @staticmethod
    def _run(args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(args, capture_output=True, text=True, timeout=3)

    def _probe_wpctl(self) -> bool:
        try:
            result = self._run(
                ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"]
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _probe_pactl(self) -> bool:
        try:
            result = self._run(
                ["pactl", "get-sink-volume", "@DEFAULT_SINK@"]
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _probe_amixer(self) -> bool:
        try:
            result = self._run(["amixer", "get", "Master"])
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def available(self) -> bool:
        return self.backend is not None

    def adjust(self, delta: float = 0.05) -> bool:
        """Change the default sink volume. Positive is louder."""
        if not self.backend:
            return False
        amount = max(1, min(100, round(abs(delta) * 100)))
        if self.backend == "wpctl":
            sign = "+" if delta >= 0 else "-"
            args = [
                "wpctl",
                "set-volume",
                "@DEFAULT_AUDIO_SINK@",
                f"{amount}%{sign}",
            ]
        elif self.backend == "pactl":
            sign = "+" if delta >= 0 else "-"
            args = [
                "pactl",
                "set-sink-volume",
                "@DEFAULT_SINK@",
                f"{sign}{amount}%",
            ]
        elif self.backend == "amixer":
            sign = "+" if delta >= 0 else "-"
            args = ["amixer", "-q", "sset", "Master", f"{amount}%{sign}"]
        else:
            return False

        try:
            result = self._run(args)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.last_error = str(exc)
            return False
        if result.returncode != 0:
            self.last_error = (result.stdout + result.stderr).strip()
            return False
        self.last_error = ""
        return True

    def toggle_mute(self) -> bool:
        if not self.backend:
            return False
        if self.backend == "wpctl":
            args = [
                "wpctl",
                "set-mute",
                "@DEFAULT_AUDIO_SINK@",
                "toggle",
            ]
        elif self.backend == "pactl":
            args = [
                "pactl",
                "set-sink-mute",
                "@DEFAULT_SINK@",
                "toggle",
            ]
        elif self.backend == "amixer":
            args = ["amixer", "-q", "sset", "Master", "toggle"]
        else:
            return False

        try:
            result = self._run(args)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.last_error = str(exc)
            return False
        if result.returncode != 0:
            self.last_error = (result.stdout + result.stderr).strip()
            return False
        self.last_error = ""
        return True
