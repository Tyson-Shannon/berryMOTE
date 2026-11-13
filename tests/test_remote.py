from __future__ import annotations

import Remote


class FakeBackend:
    name = "fake"

    def __init__(self):
        self.calls = []
        self.closed = False

    def move_relative(self, dx, dy):
        self.calls.append(("move", dx, dy))

    def click(self, button="left"):
        self.calls.append(("click", button))

    def scroll(self, dy):
        self.calls.append(("scroll", dy))

    def type_text(self, text):
        self.calls.append(("type", text))

    def press_key(self, key):
        self.calls.append(("key", key))

    def media_key(self, key):
        self.calls.append(("media", key))

    def close(self):
        self.closed = True


class FakeAudio:
    backend = "fake"

    def __init__(self):
        self.calls = []

    def adjust(self, delta):
        self.calls.append(("adjust", delta))
        return True

    def toggle_mute(self):
        self.calls.append(("mute",))
        return True


def make_remote(monkeypatch, pin="", backend=None, backend_error=""):
    audio = FakeAudio()
    monkeypatch.setattr(Remote, "AudioController", lambda: audio)
    backend = backend if backend is not None else FakeBackend()
    remote = Remote.Remote(
        port=5001,
        pin=pin,
        backend=backend,
        backend_error=backend_error,
    )
    return remote, remote.app.test_client(), backend, audio


def login(client, pin="1234"):
    return client.post("/login", data={"pin": pin})


def test_remote_without_pin_serves_remote(monkeypatch):
    _, client, _, _ = make_remote(monkeypatch)

    response = client.get("/")

    assert response.status_code == 200
    assert b"berryMOTE" in response.data
    assert client.get("/health").get_json()["pin_required"] is False


def test_remote_uses_input_events_for_mobile_typing(monkeypatch):
    _, client, _, _ = make_remote(monkeypatch)

    html = client.get("/").data.decode()

    assert '<input id="keystroke-catcher"' in html
    assert 'addEventListener("input"' in html
    assert 'contenteditable="true"' not in html


def test_remote_with_pin_requires_login(monkeypatch):
    _, client, backend, _ = make_remote(monkeypatch, pin="1234")

    assert client.get("/").status_code == 302
    assert client.get("/health").status_code == 200
    assert client.post("/action", json={"action": "click"}).status_code == 401
    assert login(client, "wrong").status_code == 200
    assert client.get("/").status_code == 302

    assert login(client).status_code == 302
    assert client.get("/").status_code == 200
    assert client.post("/action", json={"action": "click"}).status_code == 200
    assert backend.calls == [("click", "left")]

    assert client.get("/logout").status_code == 302
    assert client.get("/").status_code == 302


def test_login_rate_limit(monkeypatch):
    _, client, _, _ = make_remote(monkeypatch, pin="1234")

    for _ in range(Remote.MAX_LOGIN_FAILURES):
        response = login(client, "wrong")
        assert b"Incorrect PIN" in response.data

    response = login(client)
    assert b"Too many attempts" in response.data
    assert client.get("/").status_code == 302


def test_move_is_clamped(monkeypatch):
    _, client, backend, _ = make_remote(monkeypatch)

    response = client.post(
        "/action", json={"action": "move", "data": {"dx": 99999, "dy": -99999}}
    )

    assert response.status_code == 200
    assert backend.calls == [("move", 500, -500)]


def test_click_scroll_and_validation(monkeypatch):
    _, client, backend, _ = make_remote(monkeypatch)

    assert client.post("/action", json={"action": "click"}).status_code == 200
    assert (
        client.post(
            "/action", json={"action": "click", "data": {"button": "middle"}}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/action", json={"action": "click", "data": {"button": "back"}}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/action", json={"action": "scroll", "data": {"dy": 99}}
        ).status_code
        == 200
    )

    assert backend.calls == [("click", "left"), ("click", "middle"), ("scroll", 20)]


def test_type_truncation_and_backspace_clamping(monkeypatch):
    _, client, backend, _ = make_remote(monkeypatch)

    long_text = "a" * (Remote.MAX_TEXT_LENGTH + 10)
    assert (
        client.post("/action", json={"action": "type", "data": long_text}).status_code
        == 200
    )
    assert (
        client.post("/action", json={"action": "backspace", "data": 999}).status_code
        == 200
    )
    assert (
        client.post("/action", json={"action": "backspace", "data": 0}).status_code
        == 200
    )

    assert backend.calls[0] == ("type", "a" * Remote.MAX_TEXT_LENGTH)
    assert backend.calls[1:] == [("key", "backspace")] * 201


def test_keys_and_media(monkeypatch):
    _, client, backend, _ = make_remote(monkeypatch)

    assert (
        client.post("/action", json={"action": "key", "data": "return"}).status_code
        == 200
    )
    assert (
        client.post(
            "/action", json={"action": "media", "data": {"key": "play"}}
        ).status_code
        == 200
    )
    assert (
        client.post("/action", json={"action": "key", "data": "f13"}).status_code
        == 400
    )

    assert backend.calls == [("key", "enter"), ("media", "playpause")]


def test_volume_prefers_media_keys(monkeypatch):
    _, client, backend, audio = make_remote(monkeypatch)

    assert client.post("/action", json={"action": "volume_up"}).status_code == 200
    assert client.post("/action", json={"action": "volume_down"}).status_code == 200
    assert (
        client.post("/action", json={"action": "volume_toggle_mute"}).status_code
        == 200
    )
    assert backend.calls == [
        ("media", "volumeup"),
        ("media", "volumedown"),
        ("media", "mute"),
    ]
    assert audio.calls == []


def test_volume_falls_back_to_system_mixer(monkeypatch):
    _, client, backend, audio = make_remote(monkeypatch)

    def fail_media(key):
        raise Remote.InputBackendError("media keys unavailable")

    backend.media_key = fail_media

    assert client.post("/action", json={"action": "volume_up"}).status_code == 200
    assert client.post("/action", json={"action": "volume_down"}).status_code == 200
    assert (
        client.post("/action", json={"action": "volume_toggle_mute"}).status_code
        == 200
    )

    assert audio.calls == [("adjust", 0.05), ("adjust", -0.05), ("mute",)]


def test_invalid_requests_and_unknown_action(monkeypatch):
    _, client, _, _ = make_remote(monkeypatch)

    assert (
        client.post(
            "/action", data="not json", content_type="application/json"
        ).status_code
        == 400
    )
    assert client.post("/action", json={"action": "nope"}).status_code == 400


def test_missing_backend_returns_503(monkeypatch):
    remote, client, _, _ = make_remote(monkeypatch)
    remote.backend = None
    remote.backend_error = "no backend"

    response = client.post("/action", json={"action": "click"})

    assert response.status_code == 503
    assert response.get_json()["error"] == "no backend"
    assert client.get("/health").get_json()["backend_available"] is False


def test_shutdown_closes_backend(monkeypatch):
    remote, _, backend, _ = make_remote(monkeypatch)

    remote.shutdown()

    assert backend.closed is True
    assert remote.backend is None


def test_start_uses_the_bound_port(monkeypatch):
    remote, _, backend, _ = make_remote(monkeypatch)
    remote.port = 0

    remote.start()
    try:
        assert remote.running
        assert remote.port > 0
    finally:
        remote.shutdown()

    assert backend.closed is True
