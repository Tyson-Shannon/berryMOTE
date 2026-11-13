"""berryMOTE phone remote.

The remote is a small Flask app served on the LAN. Input is delegated to an
InputBackend so Wayland sessions can use uinput while Windows/X11 use pynput.
"""

from __future__ import annotations

import hmac
import secrets
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.serving import WSGIRequestHandler, make_server

from Audio import AudioController
from InputBackends import (
    InputBackend,
    InputBackendError,
    normalize_key,
    try_select_backend,
)


BASE_DIR = Path(__file__).resolve().parent


def resource_path(relative_path: str) -> Path:
    """Return a bundled data path, or the source-tree path when not frozen."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / relative_path
    return BASE_DIR / relative_path


MAX_TEXT_LENGTH = 2000
MAX_LOGIN_FAILURES = 5
LOGIN_WINDOW_SECONDS = 60


class QuietRequestHandler(WSGIRequestHandler):
    def log_request(self, code="-", size="-") -> None:
        return None


class Remote:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 5000,
        pin: Optional[str] = None,
        backend: Optional[InputBackend] = None,
        backend_error: Optional[str] = None,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.pin = str(pin).strip() if pin else ""
        self.backend = backend
        self.backend_error = backend_error or ""
        if self.backend is None and not self.backend_error:
            self.backend, self.backend_error = try_select_backend()

        self.audio = AudioController()
        self._server = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._login_failures: dict[str, list[float]] = {}

        self.app = Flask(
            __name__,
            template_folder=str(resource_path("templates")),
            static_folder=str(resource_path("static")),
        )
        self.app.secret_key = secrets.token_hex(32)
        self.app.config.update(
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="Strict",
            MAX_CONTENT_LENGTH=64 * 1024,
        )
        self._register_routes()

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------
    def _register_routes(self) -> None:
        self.app.add_url_rule("/", "index", self.index)
        self.app.add_url_rule(
            "/login", "login", self.login, methods=["GET", "POST"]
        )
        self.app.add_url_rule("/logout", "logout", self.logout)
        self.app.add_url_rule("/health", "health", self.health)
        self.app.add_url_rule(
            "/action", "action", self.action, methods=["POST"]
        )
        self.app.before_request(self._authenticate)
        self.app.after_request(self._security_headers)

    def _authorized(self) -> bool:
        return not self.pin or session.get("authorized") is True

    def _authenticate(self):
        if request.endpoint in {"login", "logout", "health", "static"}:
            return None
        if self._authorized():
            return None
        if request.endpoint == "action":
            return jsonify(ok=False, error="Unauthorized"), 401
        return redirect(url_for("login"))

    @staticmethod
    def _security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.endpoint in {"index", "login"}:
            response.headers["Cache-Control"] = "no-store"
        return response

    def index(self):
        if not self._authorized():
            return redirect(url_for("login"))
        return render_template(
            "remote.html",
            pin_required=bool(self.pin),
        )

    def login(self):
        error = ""
        if request.method == "POST":
            if self._login_rate_limited():
                error = "Too many attempts. Wait a minute and try again."
            else:
                supplied = str(request.form.get("pin", "")).strip()
                if self.pin and hmac.compare_digest(supplied, self.pin):
                    session["authorized"] = True
                    session.permanent = False
                    with self._lock:
                        self._login_failures.pop(self._client_ip(), None)
                    return redirect(url_for("index"))
                error = "Incorrect PIN."
                with self._lock:
                    self._login_failures.setdefault(
                        self._client_ip(), []
                    ).append(time.monotonic())
        return render_template(
            "login.html",
            error=error,
            pin_required=bool(self.pin),
        )

    def logout(self):
        session.clear()
        return redirect(url_for("login" if self.pin else "index"))

    def health(self):
        return jsonify(
            ok=True,
            backend=self.backend.name if self.backend else None,
            backend_available=self.backend is not None,
            backend_error=self.backend_error,
            audio=self.audio.backend,
            pin_required=bool(self.pin),
            version="2.0.0",
        )

    def action(self):
        if self.backend is None:
            return (
                jsonify(
                    ok=False,
                    error=self.backend_error
                    or "No input backend is available.",
                ),
                503,
            )

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(ok=False, error="Invalid JSON body."), 400

        action = str(payload.get("action", "")).strip()
        data: Any = payload.get("data", "")

        try:
            self._dispatch(action, data)
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        except InputBackendError as exc:
            return jsonify(ok=False, error=str(exc)), 503
        except Exception as exc:  # keep the remote alive on unexpected failures
            return jsonify(ok=False, error=f"Action failed: {exc}"), 500
        return jsonify(ok=True)

    # ------------------------------------------------------------------
    # Action dispatch
    # ------------------------------------------------------------------
    def _dispatch(self, action: str, data: Any) -> None:
        backend = self.backend
        assert backend is not None

        if action == "move":
            dx, dy = self._delta(data)
            backend.move_relative(dx, dy)
        elif action == "click":
            backend.click(self._button(data))
        elif action in {"scroll", "scroll_up", "scroll_down"}:
            if action == "scroll_up":
                amount = 1
            elif action == "scroll_down":
                amount = -1
            else:
                amount = self._number(
                    data.get("dy", 0) if isinstance(data, dict) else data,
                    "scroll amount",
                    minimum=-20,
                    maximum=20,
                )
            backend.scroll(int(amount))
        elif action == "type":
            text = str(data) if data is not None else ""
            if len(text) > MAX_TEXT_LENGTH:
                text = text[:MAX_TEXT_LENGTH]
            backend.type_text(text)
        elif action == "backspace":
            count = 1
            if isinstance(data, (int, float)):
                count = max(1, min(200, int(data)))
            elif isinstance(data, str) and data.isdigit():
                count = max(1, min(200, int(data)))
            for _ in range(count):
                backend.press_key("backspace")
        elif action == "key":
            key = data.get("key") if isinstance(data, dict) else data
            backend.press_key(normalize_key(str(key)))
        elif action == "media":
            key = data.get("key") if isinstance(data, dict) else data
            backend.media_key(normalize_key(str(key)))
        elif action == "volume_up":
            self._volume(0.05)
        elif action == "volume_down":
            self._volume(-0.05)
        elif action == "volume_toggle_mute":
            self._mute()
        else:
            raise ValueError(f"Unknown action: {action!r}")

    @staticmethod
    def _number(
        value: Any,
        name: str,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
    ) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid {name}.") from exc
        if minimum is not None and number < minimum:
            number = minimum
        if maximum is not None and number > maximum:
            number = maximum
        return number

    def _delta(self, data: Any) -> tuple[int, int]:
        if not isinstance(data, dict):
            raise ValueError("Move data must contain dx and dy.")
        dx = int(self._number(data.get("dx", 0), "dx", -500, 500))
        dy = int(self._number(data.get("dy", 0), "dy", -500, 500))
        return dx, dy

    def _button(self, data: Any) -> str:
        button = (
            str(data.get("button", "left"))
            if isinstance(data, dict)
            else str(data or "left")
        ).lower()
        if button not in {"left", "middle", "right"}:
            raise ValueError(f"Unsupported mouse button: {button!r}")
        return button

    def _volume(self, delta: float) -> None:
        backend = self.backend
        assert backend is not None
        try:
            backend.media_key("volumeup" if delta > 0 else "volumedown")
        except (InputBackendError, ValueError):
            self.audio.adjust(delta)

    def _mute(self) -> None:
        backend = self.backend
        assert backend is not None
        try:
            backend.media_key("mute")
        except (InputBackendError, ValueError):
            self.audio.toggle_mute()

    # ------------------------------------------------------------------
    # Login helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _client_ip() -> str:
        return request.remote_addr or "unknown"

    def _login_rate_limited(self) -> bool:
        with self._lock:
            now = time.monotonic()
            attempts = [
                stamp
                for stamp in self._login_failures.get(self._client_ip(), [])
                if now - stamp < LOGIN_WINDOW_SECONDS
            ]
            self._login_failures[self._client_ip()] = attempts
            return len(attempts) >= MAX_LOGIN_FAILURES

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._server is not None

    def start(self) -> None:
        with self._lock:
            if self._server is not None:
                return
            self._server = make_server(
                self.host,
                self.port,
                self.app,
                threaded=True,
                request_handler=QuietRequestHandler,
            )
            self.port = int(self._server.server_port)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                name="berrymote-remote",
                daemon=True,
            )
            self._thread.start()

    def shutdown(self) -> None:
        with self._lock:
            server = self._server
            thread = self._thread
            self._server = None
            self._thread = None
        if server is not None:
            server.shutdown()
        if thread is not None:
            thread.join(timeout=3)
        backend = self.backend
        self.backend = None
        if backend is not None:
            backend.close()

    def run(self) -> None:
        """Blocking entry point retained for compatibility."""
        self.start()
        if self._thread is not None:
            self._thread.join()
