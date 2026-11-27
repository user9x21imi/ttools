from types import SimpleNamespace

from tspotify import sharing


def test_share_url_does_not_use_tracking_or_private_urls():
    assert sharing.share_url({"uri": "spotify:playlist:abc123"}) == "https://open.spotify.com/playlist/abc123"
    assert sharing.share_url({"type": "track", "id": "abc"}) == "https://open.spotify.com/track/abc"
    assert sharing.share_url({"type": "artist", "id": "artist123"}) == "https://open.spotify.com/artist/artist123"
    assert sharing.share_url({"id": "../credentials"}) == ""
    assert sharing.share_url({"external_urls": {"spotify": "https://bad.example"}}) == ""


def test_clipboard_failure_is_not_reported_as_copied(monkeypatch):
    monkeypatch.setattr(sharing.shutil, "which", lambda _: None)
    assert "недоступен" in sharing.copy_link("https://open.spotify.com/track/abc")


def test_macos_clipboard_uses_stdin_not_shell_interpolation(monkeypatch):
    calls = []
    monkeypatch.setattr(sharing.sys, "platform", "darwin")
    monkeypatch.setattr(sharing.shutil, "which", lambda _: "/usr/bin/pbcopy")
    monkeypatch.setattr(
        sharing.subprocess, "run", lambda *a, **kw: calls.append((a, kw)) or SimpleNamespace(returncode=0)
    )
    assert "скопирована" in sharing.copy_link("https://open.spotify.com/track/abc")
    assert calls[0][0] == (["pbcopy"],)
    assert calls[0][1]["input"] == "https://open.spotify.com/track/abc"


def test_internal_jam_join_token_uses_spotify_public_socialsession_route():
    assert (
        sharing.jam_invite_url("hm://social-connect/v2/sessions/join/abcdefgh12345678")
        == "https://open.spotify.com/socialsession/abcdefgh12345678"
    )
    import pytest

    for value in (
        "https://bad.example/invite",
        "hm://social-connect/v2/sessions/info/abcdefgh12345678",
        "hm://social-connect/v2/sessions/join/../credentials",
    ):
        with pytest.raises(ValueError):
            sharing.jam_invite_url(value)
