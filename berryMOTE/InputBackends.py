"""Cross-platform input injection for berryMOTE.

Windows and X11 use pynput. Wayland has no generic input-injection API, so
berryMOTE uses uinput-based helpers there:

* dotool (preferred): no daemon, fast persistent stdin protocol
* native uinput: no helper process or per-event overhead
* ydotool (fallback): requires the ydotoold daemon

Both helpers are external system programs; berryMOTE only invokes them.
"""

from __future__ import annotations

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]
import os
import shutil
import struct
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol


CANONICAL_KEYS = {
    "enter",
    "esc",
    "backspace",
    "tab",
    "space",
    "up",
    "down",
    "left",
    "right",
    "home",
    "end",
    "pageup",
    "pagedown",
    "delete",
    "back",
    "menu",
    "playpause",
    "next",
    "previous",
    "stop",
    "volumeup",
    "volumedown",
    "mute",
}

_KEY_ALIASES = {
    "escape": "esc",
    "return": "enter",
    "page_up": "pageup",
    "page_down": "pagedown",
    "del": "delete",
    "play_pause": "playpause",
    "play": "playpause",
    "next_song": "next",
    "nextsong": "next",
    "prev": "previous",
    "previous_song": "previous",
    "previoussong": "previous",
    "volume_up": "volumeup",
    "volume_down": "volumedown",
    "volume_mute": "mute",
    "mute_toggle": "mute",
}

_MEDIA_KEYS = {
    "playpause": "playpause",
    "next": "next",
    "previous": "previous",
    "stop": "stop",
    "volumeup": "volumeup",
    "volumedown": "volumedown",
    "mute": "mute",
}


def normalize_key(key: str) -> str:
    """Return a canonical key name or raise ValueError."""
    value = str(key).strip().lower().replace("-", "_").replace(" ", "_")
    value = _KEY_ALIASES.get(value, value)
    if value not in CANONICAL_KEYS:
        raise ValueError(f"Unsupported key: {key!r}")
    return value


class InputBackendError(RuntimeError):
    """Raised when an input backend cannot perform an action."""


class BackendUnavailable(InputBackendError):
    """Raised when no usable input backend is installed/configured."""


class InputBackend(Protocol):
    name: str

    def move_relative(self, dx: int, dy: int) -> None:
        ...

    def click(self, button: str = "left") -> None:
        ...

    def scroll(self, dy: int) -> None:
        ...

    def type_text(self, text: str) -> None:
        ...

    def press_key(self, key: str) -> None:
        ...

    def media_key(self, key: str) -> None:
        ...

    def close(self) -> None:
        ...


def _is_wayland() -> bool:
    return (
        os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
        or bool(os.environ.get("WAYLAND_DISPLAY"))
    )


def _env(name: str, default: str = "") -> str:
    """Read a berryMOTE setting, falling back to the berryTV name."""
    return os.environ.get(f"BERRYMOTE_{name}") or os.environ.get(
        f"BERRYTV_{name}"
    ) or default


def _uinput_path() -> Path:
    return Path(_env("UINPUT", "/dev/uinput"))


def uinput_writable() -> bool:
    path = _uinput_path()
    return path.exists() and os.access(path, os.W_OK)


def _uinput_hint() -> str:
    path = _uinput_path()
    if not path.exists():
        return f"{path} does not exist. Load the uinput kernel module."
    if not os.access(path, os.W_OK):
        return (
            f"{path} is not writable by this user. Add the user to the input "
            "group and reload the udev rule, then log out and back in."
        )
    return f"{path} is writable."


class PynputBackend:
    """Input backend for Windows, macOS and X11 sessions."""

    name = "pynput"

    def __init__(self) -> None:
        if sys.platform.startswith("linux") and _is_wayland():
            raise BackendUnavailable(
                "pynput cannot inject input into native Wayland applications."
            )
        try:
            from pynput.keyboard import Controller as KeyboardController
            from pynput.keyboard import Key, KeyCode
            from pynput.mouse import Button
            from pynput.mouse import Controller as MouseController
        except Exception as exc:  # pragma: no cover - platform dependent
            raise BackendUnavailable(f"pynput is not usable: {exc}") from exc

        try:
            self._mouse = MouseController()
            self._keyboard = KeyboardController()
        except Exception as exc:  # pragma: no cover - display dependent
            raise BackendUnavailable(f"Could not open the input device: {exc}") from exc

        self._Key = Key
        self._KeyCode = KeyCode
        self._Button = Button
        self._keys = self._build_key_map(Key)
        self._buttons = {
            "left": Button.left,
            "middle": Button.middle,
            "right": Button.right,
        }

    @staticmethod
    def _build_key_map(Key) -> dict[str, object]:
        names = {
            "enter": "enter",
            "esc": "esc",
            "backspace": "backspace",
            "tab": "tab",
            "space": "space",
            "up": "up",
            "down": "down",
            "left": "left",
            "right": "right",
            "home": "home",
            "end": "end",
            "pageup": "page_up",
            "pagedown": "page_down",
            "delete": "delete",
            "playpause": "media_play_pause",
            "next": "media_next",
            "previous": "media_previous",
            "stop": "media_stop",
            "volumeup": "media_volume_up",
            "volumedown": "media_volume_down",
            "mute": "media_volume_mute",
            "back": "browser_back",
            "menu": "menu",
        }
        result = {}
        for canonical, attr in names.items():
            value = getattr(Key, attr, None)
            if value is not None:
                result[canonical] = value
        return result

    def move_relative(self, dx: int, dy: int) -> None:
        if not dx and not dy:
            return
        try:
            x, y = self._mouse.position
            self._mouse.position = (x + int(dx), y + int(dy))
        except Exception as exc:  # pragma: no cover - platform dependent
            raise InputBackendError(f"Mouse move failed: {exc}") from exc

    def click(self, button: str = "left") -> None:
        try:
            self._mouse.click(self._buttons[button])
        except KeyError as exc:
            raise ValueError(f"Unsupported mouse button: {button!r}") from exc
        except Exception as exc:  # pragma: no cover - platform dependent
            raise InputBackendError(f"Mouse click failed: {exc}") from exc

    def scroll(self, dy: int) -> None:
        if not dy:
            return
        try:
            self._mouse.scroll(0, int(dy))
        except Exception as exc:  # pragma: no cover - platform dependent
            raise InputBackendError(f"Scroll failed: {exc}") from exc

    def type_text(self, text: str) -> None:
        if not text:
            return
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        try:
            for index, part in enumerate(text.split("\n")):
                if index:
                    self.press_key("enter")
                if part:
                    self._keyboard.type(part)
        except Exception as exc:  # pragma: no cover - platform dependent
            raise InputBackendError(f"Typing failed: {exc}") from exc

    def press_key(self, key: str) -> None:
        canonical = normalize_key(key)
        value = self._keys.get(canonical)
        if value is None:
            raise ValueError(f"Key {canonical!r} is not supported by pynput.")
        try:
            self._keyboard.press(value)
            self._keyboard.release(value)
        except Exception as exc:  # pragma: no cover - platform dependent
            raise InputBackendError(f"Key press failed: {exc}") from exc

    def media_key(self, key: str) -> None:
        canonical = _MEDIA_KEYS.get(key, key)
        self.press_key(canonical)

    def close(self) -> None:
        return None


_UI_DEV_CREATE = 0x5501
_UI_DEV_DESTROY = 0x5502
_UI_SET_EVBIT = 0x40045564
_UI_SET_KEYBIT = 0x40045565
_UI_SET_RELBIT = 0x40045566

_EV_SYN = 0x00
_EV_KEY = 0x01
_EV_REL = 0x02
_SYN_REPORT = 0

_REL_X = 0x00
_REL_Y = 0x01
_REL_HWHEEL = 0x06
_REL_WHEEL = 0x08

_BTN_LEFT = 0x110
_BTN_RIGHT = 0x111
_BTN_MIDDLE = 0x112

_KEY_LEFTSHIFT = 42

_LINUX_KEYCODES = {
    "enter": 28,
    "esc": 1,
    "backspace": 14,
    "tab": 15,
    "space": 57,
    "up": 103,
    "down": 108,
    "left": 105,
    "right": 106,
    "home": 102,
    "end": 107,
    "pageup": 104,
    "pagedown": 109,
    "delete": 111,
    "back": 158,
    "menu": 139,
    "playpause": 164,
    "next": 163,
    "previous": 165,
    "stop": 166,
    "volumeup": 115,
    "volumedown": 114,
    "mute": 113,
}

_TEXT_KEYS = {
    "1": (2, False),
    "2": (3, False),
    "3": (4, False),
    "4": (5, False),
    "5": (6, False),
    "6": (7, False),
    "7": (8, False),
    "8": (9, False),
    "9": (10, False),
    "0": (11, False),
    "-": (12, False),
    "=": (13, False),
    "[": (26, False),
    "]": (27, False),
    ";": (39, False),
    "'": (40, False),
    "`": (41, False),
    "\\": (43, False),
    ",": (51, False),
    ".": (52, False),
    "/": (53, False),
    " ": (57, False),
    "a": (30, False),
    "b": (48, False),
    "c": (46, False),
    "d": (32, False),
    "e": (18, False),
    "f": (33, False),
    "g": (34, False),
    "h": (35, False),
    "i": (23, False),
    "j": (36, False),
    "k": (37, False),
    "l": (38, False),
    "m": (50, False),
    "n": (49, False),
    "o": (24, False),
    "p": (25, False),
    "q": (16, False),
    "r": (19, False),
    "s": (31, False),
    "t": (20, False),
    "u": (22, False),
    "v": (47, False),
    "w": (17, False),
    "x": (45, False),
    "y": (21, False),
    "z": (44, False),
    "!": (2, True),
    "@": (3, True),
    "#": (4, True),
    "$": (5, True),
    "%": (6, True),
    "^": (7, True),
    "&": (8, True),
    "*": (9, True),
    "(": (10, True),
    ")": (11, True),
    "_": (12, True),
    "+": (13, True),
    "{": (26, True),
    "}": (27, True),
    ":": (39, True),
    '"': (40, True),
    "~": (41, True),
    "|": (43, True),
    "<": (51, True),
    ">": (52, True),
    "?": (53, True),
}


def _text_key(char: str) -> Optional[tuple[int, bool]]:
    if char in "\r\n":
        return (_LINUX_KEYCODES["enter"], False)
    if char == "\t":
        return (_LINUX_KEYCODES["tab"], False)
    if char in _TEXT_KEYS:
        return _TEXT_KEYS[char]
    lower = char.lower()
    if lower != char and lower in _TEXT_KEYS:
        code, _ = _TEXT_KEYS[lower]
        return (code, True)
    return None


class UinputBackend:
    """Native Linux uinput backend.

    A mouse and a keyboard are registered as separate virtual devices. Keeping
    them separate matters on Wayland: compositors classify a device with both
    pointer axes and many keys as a pointer, so keyboard events from a combined
    device can be ignored. Writing directly to uinput avoids per-event process
    overhead, keeping pointer movement smooth.
    """

    name = "uinput"

    def __init__(self) -> None:
        if not sys.platform.startswith("linux"):
            raise BackendUnavailable("uinput is only available on Linux.")
        if not uinput_writable():
            raise BackendUnavailable(f"uinput is not available. {_uinput_hint()}")

        self._lock = threading.Lock()
        self._event = struct.Struct("@llHHi")
        self._buttons = {
            "left": _BTN_LEFT,
            "middle": _BTN_MIDDLE,
            "right": _BTN_RIGHT,
        }
        self._mouse_fd: Optional[int] = None
        self._keyboard_fd: Optional[int] = None

        key_codes = set(_LINUX_KEYCODES.values())
        key_codes.update(code for code, _ in _TEXT_KEYS.values())
        key_codes.add(_KEY_LEFTSHIFT)

        try:
            self._mouse_fd = self._create_device(
                "berryMOTE virtual mouse",
                set(self._buttons.values()),
                (_REL_X, _REL_Y, _REL_WHEEL, _REL_HWHEEL),
            )
            self._keyboard_fd = self._create_device(
                "berryMOTE virtual keyboard",
                key_codes,
                (),
            )
            time.sleep(0.05)
        except Exception as exc:
            self.close()
            raise BackendUnavailable(
                f"Could not create uinput device: {exc}"
            ) from exc

    def _create_device(
        self,
        name: str,
        key_codes: set[int],
        rel_codes: tuple[int, ...],
    ) -> int:
        fd = os.open(_uinput_path(), os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(fd, _UI_SET_EVBIT, _EV_SYN)
            if key_codes:
                fcntl.ioctl(fd, _UI_SET_EVBIT, _EV_KEY)
                for code in sorted(key_codes):
                    fcntl.ioctl(fd, _UI_SET_KEYBIT, code)
            if rel_codes:
                fcntl.ioctl(fd, _UI_SET_EVBIT, _EV_REL)
                for code in rel_codes:
                    fcntl.ioctl(fd, _UI_SET_RELBIT, code)

            device = struct.pack(
                "80sHHHHI" + "64i" * 4,
                name.encode("utf-8")[:79],
                0x03,
                0x1234,
                0x5678,
                1,
                0,
                *([0] * 256),
            )
            os.write(fd, device)
            fcntl.ioctl(fd, _UI_DEV_CREATE)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        return fd

    def _write(
        self,
        fd: int,
        event_type: int,
        code: int,
        value: int,
    ) -> None:
        os.write(fd, self._event.pack(0, 0, event_type, code, value))

    def _sync(self, fd: int) -> None:
        self._write(fd, _EV_SYN, _SYN_REPORT, 0)

    def move_relative(self, dx: int, dy: int) -> None:
        dx, dy = int(dx), int(dy)
        if not dx and not dy:
            return
        fd = self._mouse_fd
        if fd is None:
            return
        try:
            with self._lock:
                if dx:
                    self._write(fd, _EV_REL, _REL_X, dx)
                if dy:
                    self._write(fd, _EV_REL, _REL_Y, dy)
                self._sync(fd)
        except OSError as exc:
            raise InputBackendError(f"Mouse move failed: {exc}") from exc

    def click(self, button: str = "left") -> None:
        try:
            code = self._buttons[button]
        except KeyError as exc:
            raise ValueError(f"Unsupported mouse button: {button!r}") from exc
        fd = self._mouse_fd
        if fd is None:
            return
        try:
            with self._lock:
                self._write(fd, _EV_KEY, code, 1)
                self._sync(fd)
                self._write(fd, _EV_KEY, code, 0)
                self._sync(fd)
        except OSError as exc:
            raise InputBackendError(f"Mouse click failed: {exc}") from exc

    def scroll(self, dy: int) -> None:
        if not dy:
            return
        fd = self._mouse_fd
        if fd is None:
            return
        try:
            with self._lock:
                self._write(fd, _EV_REL, _REL_WHEEL, int(dy))
                self._sync(fd)
        except OSError as exc:
            raise InputBackendError(f"Scroll failed: {exc}") from exc

    def type_text(self, text: str) -> None:
        if not text:
            return
        fd = self._keyboard_fd
        if fd is None:
            return
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        try:
            with self._lock:
                for char in text:
                    key = _text_key(char)
                    if key is None:
                        continue
                    code, shift = key
                    if shift:
                        self._write(fd, _EV_KEY, _KEY_LEFTSHIFT, 1)
                    self._write(fd, _EV_KEY, code, 1)
                    self._write(fd, _EV_KEY, code, 0)
                    if shift:
                        self._write(fd, _EV_KEY, _KEY_LEFTSHIFT, 0)
                    self._sync(fd)
        except OSError as exc:
            raise InputBackendError(f"Typing failed: {exc}") from exc

    def press_key(self, key: str) -> None:
        canonical = normalize_key(key)
        code = _LINUX_KEYCODES.get(canonical)
        if code is None:
            raise ValueError(f"Key {canonical!r} is not supported by uinput.")
        fd = self._keyboard_fd
        if fd is None:
            return
        try:
            with self._lock:
                self._write(fd, _EV_KEY, code, 1)
                self._sync(fd)
                self._write(fd, _EV_KEY, code, 0)
                self._sync(fd)
        except OSError as exc:
            raise InputBackendError(f"Key press failed: {exc}") from exc

    def media_key(self, key: str) -> None:
        canonical = _MEDIA_KEYS.get(key, key)
        self.press_key(canonical)

    def close(self) -> None:
        for attr in ("_mouse_fd", "_keyboard_fd"):
            fd = getattr(self, attr, None)
            if fd is None:
                continue
            try:
                fcntl.ioctl(fd, _UI_DEV_DESTROY)
            except OSError:
                pass
            try:
                os.close(fd)
            except OSError:
                pass
            setattr(self, attr, None)

    def __del__(self) -> None:  # pragma: no cover - best effort
        self.close()


class _DotoolCommon:
    """Shared action formatting for dotool."""

    name = "dotool"

    _BUTTONS = {"left", "middle", "right"}
    _KEY_NAMES = {
        "enter": "enter",
        "esc": "esc",
        "backspace": "backspace",
        "tab": "tab",
        "space": "space",
        "up": "up",
        "down": "down",
        "left": "left",
        "right": "right",
        "home": "home",
        "end": "end",
        "pageup": "pageup",
        "pagedown": "pagedown",
        "delete": "delete",
        "back": "back",
        "menu": "menu",
        "playpause": "playpause",
        "next": "nextsong",
        "previous": "previoussong",
        "stop": "stopcd",
        "volumeup": "volumeup",
        "volumedown": "volumedown",
        "mute": "mute",
    }

    def _action_lines(self, action: str, text: str) -> list[str]:
        if action == "move":
            return [text]
        if action == "click":
            return [text]
        if action == "scroll":
            return [text]
        if action == "key":
            return [text]
        if action == "type":
            lines = []
            parts = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            for index, part in enumerate(parts):
                if index:
                    lines.append("key enter")
                if part:
                    lines.append(f"type {part}")
            return lines
        raise ValueError(f"Unknown dotool action: {action}")


class DotoolBackend(_DotoolCommon):
    """Persistent dotool process.

    dotool reads newline-delimited actions from stdin. Keeping one process
    alive avoids re-registering a virtual device for every trackpad event.
    """

    def __init__(self, binary: Optional[str] = None) -> None:
        self.binary = binary or shutil.which("dotool") or ""
        if not self.binary:
            raise BackendUnavailable("dotool was not found on PATH.")
        if not uinput_writable():
            raise BackendUnavailable(f"dotool needs uinput access. {_uinput_hint()}")

        try:
            self._process = subprocess.Popen(
                [self.binary],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise BackendUnavailable(f"Could not start dotool: {exc}") from exc

        self._lock = threading.Lock()

        # dotool registers its virtual devices on startup. If it exits
        # immediately, surface the real error instead of failing later.
        threading.Event().wait(0.15)
        if self._process.poll() is not None:
            error = ""
            if self._process.stderr is not None:
                error = self._process.stderr.read().strip()
            raise BackendUnavailable(
                "dotool exited during startup"
                + (f": {error}" if error else f" (exit code {self._process.returncode})")
            )

    def _send(self, line: str) -> None:
        if not line:
            return
        if self._process.poll() is not None:
            error = ""
            if self._process.stderr is not None:
                error = self._process.stderr.read().strip()
            raise InputBackendError(
                "dotool is no longer running"
                + (f": {error}" if error else "")
            )
        with self._lock:
            try:
                assert self._process.stdin is not None
                self._process.stdin.write(line + "\n")
                self._process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise InputBackendError(f"dotool write failed: {exc}") from exc

    def move_relative(self, dx: int, dy: int) -> None:
        dx, dy = int(dx), int(dy)
        if not dx and not dy:
            return
        self._send(f"mousemove {dx} {dy}")

    def click(self, button: str = "left") -> None:
        if button not in self._BUTTONS:
            raise ValueError(f"Unsupported mouse button: {button!r}")
        self._send(f"click {button}")

    def scroll(self, dy: int) -> None:
        if dy:
            self._send(f"wheel {int(dy)}")

    def type_text(self, text: str) -> None:
        for line in self._action_lines("type", text):
            self._send(line)

    def press_key(self, key: str) -> None:
        canonical = normalize_key(key)
        name = self._KEY_NAMES.get(canonical)
        if not name:
            raise ValueError(f"Key {canonical!r} is not supported by dotool.")
        self._send(f"key {name}")

    def media_key(self, key: str) -> None:
        canonical = _MEDIA_KEYS.get(key, key)
        self.press_key(canonical)

    def close(self) -> None:
        process = getattr(self, "_process", None)
        if process is None:
            return
        if process.poll() is None:
            try:
                if process.stdin is not None:
                    process.stdin.close()
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        self._process = None

    def __del__(self) -> None:  # pragma: no cover - best effort
        self.close()


class YdotoolBackend:
    """ydotool fallback, using the ydotoold daemon.

    Movement is coalesced into a background worker because every ydotool
    invocation is a separate process.
    """

    name = "ydotool"

    _BUTTONS = {
        "left": "0xC0",
        "right": "0xC1",
        "middle": "0xC2",
    }
    _KEYCODES = {
        "enter": 28,
        "esc": 1,
        "backspace": 14,
        "tab": 15,
        "space": 57,
        "up": 103,
        "down": 108,
        "left": 105,
        "right": 106,
        "home": 102,
        "end": 107,
        "pageup": 104,
        "pagedown": 109,
        "delete": 111,
        "back": 158,
        "menu": 139,
        "playpause": 164,
        "next": 163,
        "previous": 165,
        "stop": 166,
        "volumeup": 115,
        "volumedown": 114,
        "mute": 113,
    }

    def __init__(self, binary: Optional[str] = None) -> None:
        self.binary = binary or shutil.which("ydotool") or ""
        self._stop = threading.Event()
        self._move_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        if not self.binary:
            raise BackendUnavailable("ydotool was not found on PATH.")
        self._check_daemon()

        self._move_lock = threading.Lock()
        self._move_pending = [0, 0]
        self._worker = threading.Thread(
            target=self._move_loop, name="ydotool-move", daemon=True
        )
        self._worker.start()

    def _check_daemon(self) -> None:
        try:
            result = subprocess.run(
                [self.binary, "debug"],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BackendUnavailable(f"Could not contact ydotoold: {exc}") from exc
        if result.returncode != 0:
            detail = (result.stdout + result.stderr).strip()
            raise BackendUnavailable(
                "ydotoold is not reachable"
                + (f": {detail}" if detail else ". Start it with: systemctl --user start ydotoold")
            )

    def _run(self, args: list[str]) -> None:
        try:
            result = subprocess.run(
                [self.binary, *args],
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InputBackendError(f"ydotool failed: {exc}") from exc
        if result.returncode != 0:
            detail = (result.stdout + result.stderr).strip()
            raise InputBackendError(
                f"ydotool {' '.join(args)} failed"
                + (f": {detail}" if detail else "")
            )

    def _take_pending(self) -> tuple[int, int]:
        with self._move_lock:
            dx, dy = self._move_pending
            self._move_pending = [0, 0]
        return dx, dy

    def _flush_moves(self) -> None:
        dx, dy = self._take_pending()
        if dx or dy:
            self._run(["mousemove", "-x", str(dx), "-y", str(dy)])

    def _move_loop(self) -> None:
        # Flush at a fixed cadence. New deltas accumulate while a previous
        # ydotool process runs, so a slow helper drops intermediate motion
        # instead of building a backlog that makes the pointer feel laggy.
        interval = 0.016
        while not self._stop.is_set():
            if self._stop.wait(interval):
                break
            self._move_event.clear()
            try:
                self._flush_moves()
            except InputBackendError:
                # A later action will surface the error to the caller.
                pass

    def _run_ordered(self, args: list[str]) -> None:
        self._flush_moves()
        self._run(args)

    def move_relative(self, dx: int, dy: int) -> None:
        dx, dy = int(dx), int(dy)
        if not dx and not dy:
            return
        with self._move_lock:
            self._move_pending[0] += dx
            self._move_pending[1] += dy
        self._move_event.set()

    def click(self, button: str = "left") -> None:
        try:
            code = self._BUTTONS[button]
        except KeyError as exc:
            raise ValueError(f"Unsupported mouse button: {button!r}") from exc
        self._run_ordered(["click", code])

    def scroll(self, dy: int) -> None:
        if not dy:
            return
        self._run_ordered(["mousemove", "--wheel", "-x", "0", "-y", str(int(dy))])

    def type_text(self, text: str) -> None:
        if not text:
            return
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        for index, part in enumerate(text.split("\n")):
            if index:
                self.press_key("enter")
            if part:
                self._run_ordered(["type", part])

    def press_key(self, key: str) -> None:
        canonical = normalize_key(key)
        code = self._KEYCODES.get(canonical)
        if code is None:
            raise ValueError(f"Key {canonical!r} is not supported by ydotool.")
        self._run_ordered(["key", f"{code}:1", f"{code}:0"])

    def media_key(self, key: str) -> None:
        canonical = _MEDIA_KEYS.get(key, key)
        self.press_key(canonical)

    def close(self) -> None:
        stop = getattr(self, "_stop", None)
        event = getattr(self, "_move_event", None)
        if stop is not None:
            stop.set()
        if event is not None:
            event.set()
        worker = getattr(self, "_worker", None)
        if worker is not None and worker.is_alive():
            worker.join(timeout=2)

    def __del__(self) -> None:  # pragma: no cover - best effort
        self.close()


@dataclass(frozen=True)
class BackendProbe:
    name: str
    available: bool
    detail: str


def probe_backends() -> list[BackendProbe]:
    """Return availability information for every backend, without starting one."""
    probes: list[BackendProbe] = []

    if sys.platform.startswith("linux"):
        wayland = _is_wayland()
        dotool = shutil.which("dotool")
        dotool_detail = (
            f"found at {dotool}; {_uinput_hint()}"
            if dotool
            else "not installed"
        )
        probes.append(
            BackendProbe(
                "dotool",
                bool(dotool) and uinput_writable(),
                dotool_detail,
            )
        )

        probes.append(
            BackendProbe(
                "uinput",
                uinput_writable(),
                "native uinput device available "
                "(no per-event process overhead)"
                if uinput_writable()
                else _uinput_hint(),
            )
        )

        ydotool = shutil.which("ydotool")
        daemon_detail = "not installed"
        daemon_ok = False
        if ydotool:
            try:
                result = subprocess.run(
                    [ydotool, "debug"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                daemon_ok = result.returncode == 0
                daemon_detail = (
                    f"found at {ydotool}; ydotoold is reachable"
                    if daemon_ok
                    else f"found at {ydotool}; ydotoold is not reachable"
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                daemon_detail = f"found at {ydotool}; error: {exc}"
        probes.append(BackendProbe("ydotool", daemon_ok, daemon_detail))

        pynput_ok = bool(os.environ.get("DISPLAY")) and not wayland
        probes.append(
            BackendProbe(
                "pynput",
                pynput_ok,
                "X11 display available"
                if pynput_ok
                else "X11 only; cannot control native Wayland apps"
                if wayland
                else "no X11 display",
            )
        )
    else:
        probes.append(
            BackendProbe(
                "pynput",
                True,
                "native Windows/macOS backend",
            )
        )

    return probes


def _build_backend(name: str) -> InputBackend:
    if name == "pynput":
        return PynputBackend()
    if name == "dotool":
        return DotoolBackend()
    if name == "uinput":
        return UinputBackend()
    if name == "ydotool":
        return YdotoolBackend()
    raise ValueError(f"Unknown input backend: {name!r}")


def _preferred_order() -> list[str]:
    if sys.platform.startswith("linux") and _is_wayland():
        return ["dotool", "uinput", "ydotool"]
    if sys.platform.startswith("linux"):
        return ["pynput", "uinput", "dotool", "ydotool"]
    return ["pynput"]


def select_backend(force: Optional[str] = None) -> InputBackend:
    """Create the best available backend or raise BackendUnavailable."""
    force = (force or _env("INPUT_BACKEND")).strip().lower()
    if force and force != "auto":
        try:
            return _build_backend(force)
        except (BackendUnavailable, ValueError) as exc:
            raise BackendUnavailable(str(exc)) from exc

    errors = []
    for name in _preferred_order():
        try:
            return _build_backend(name)
        except (BackendUnavailable, ValueError) as exc:
            errors.append(f"{name}: {exc}")

    message = "No usable input backend was found."
    if errors:
        message += "\n" + "\n".join(f"- {error}" for error in errors)
    message += "\n\n" + setup_instructions()
    raise BackendUnavailable(message)


def try_select_backend(force: Optional[str] = None) -> tuple[Optional[InputBackend], str]:
    """Like select_backend, but return (None, error) instead of raising."""
    try:
        return select_backend(force), ""
    except BackendUnavailable as exc:
        return None, str(exc)


def setup_instructions() -> str:
    if not sys.platform.startswith("linux"):
        return "Install the platform input dependencies and try again."
    return (
        "Wayland requires a uinput helper. Recommended setup:\n"
        "  dotool (preferred): https://sr.ht/~geb/dotool\n"
        "    sudo usermod -aG input \"$USER\"\n"
        "    # then log out and back in\n"
        "  or ydotool:\n"
        "    sudo apt install ydotool\n"
        "    sudo usermod -aG input \"$USER\"\n"
        "    systemctl --user enable --now ydotoold\n"
        "    # then log out and back in\n"
        "Then restart berryMOTE."
    )
