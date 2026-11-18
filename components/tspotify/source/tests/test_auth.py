from datetime import datetime, timedelta, timezone

import pytest
import httpx
from urllib.parse import parse_qs, urlsplit, urlencode

from tspotify import auth, paths


def test_callback_accepts_exact_session_and_decodes_code():
    assert auth.parse_callback("/ncspot_login?state=right&code=hello%2Bworld", "right") == "hello+world"


@pytest.mark.parametrize(
    "url",
    [
        "/ncspot_login?state=other&code=secret",
        "/ncspot_login?code=secret",
        "/login?state=right&code=secret",
        "/ncspot_login?state=right&error=access_denied",
        "/ncspot_login?state=right",
        "/favicon.ico",
    ],
)
def test_callback_rejects_other_sessions_denials_and_stray_requests(url):
    with pytest.raises(ValueError):
        auth.parse_callback(url, "right")


def test_fresh_cached_token_never_makes_network_call(monkeypatch):
    paths.private_json(
        paths.TOKEN_FILE,
        {
            "access_token": "private",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        },
    )
    monkeypatch.setattr(auth.httpx, "post", lambda *a, **k: pytest.fail("unexpected network"))
    assert auth.access_token() == "private"


def test_refresh_retains_refresh_token_if_spotify_omits_it():
    value = auth.save_token({"access_token": "new", "expires_in": 3600}, {"refresh_token": "keep"})
    assert value["refresh_token"] == "keep"
    assert paths.TOKEN_FILE.is_file()


def test_missing_login_is_a_clear_recoverable_error():
    with pytest.raises(auth.LoginRequired, match="tspotify login"):
        auth.access_token()


def test_browser_login_completes_real_loopback_callback_without_collecting_password(monkeypatch):
    def open_browser(url, **kwargs):
        query = parse_qs(urlsplit(url).query)
        assert query["code_challenge_method"] == ["S256"]
        assert "code_verifier" not in query
        callback = "http://127.0.0.1:8989/ncspot_login?" + urlencode(
            {"state": query["state"][0], "code": "test-code"}
        )
        response = httpx.get(callback, timeout=3, trust_env=False)
        assert response.status_code == 200
        return True

    monkeypatch.setattr(auth.webbrowser, "open", open_browser)
    monkeypatch.setattr(
        auth.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={
                "access_token": "fake-token-for-test",
                "refresh_token": "fake-refresh",
                "expires_in": 3600,
                "scope": auth.SCOPES,
            },
        ),
    )
    auth.login(timeout=2)
    assert auth.read_token()["access_token"] == "fake-token-for-test"


def test_qr_phone_callback_validates_the_original_session(monkeypatch):
    import qrcode

    shown = []

    class QR:
        def __init__(self, **kwargs):
            pass

        def add_data(self, value):
            shown.append(value)

        def make(self, **kwargs):
            pass

        def print_ascii(self, **kwargs):
            pass

    monkeypatch.setattr(qrcode, "QRCode", QR)

    def pasted(prompt):
        state = parse_qs(urlsplit(shown[0]).query)["state"][0]
        return "http://127.0.0.1:8989/ncspot_login?" + urlencode({"state": state, "code": "phone-code"})

    monkeypatch.setattr("builtins.input", pasted)
    monkeypatch.setattr(
        auth.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={
                "access_token": "fake-phone-token",
                "refresh_token": "fake-refresh",
                "expires_in": 3600,
            },
        ),
    )
    auth.login(qr=True, timeout=2)
    assert auth.read_token()["access_token"] == "fake-phone-token"
