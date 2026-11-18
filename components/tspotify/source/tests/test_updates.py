import hashlib
from types import SimpleNamespace

import httpx
import pytest

from tspotify import updates


def test_versions_compare_numerically_and_reject_prereleases():
    assert updates.version("v0.10.0") > updates.version("0.9.9")
    assert updates.version("v1.0.0-rc1") is None
    assert updates.version("../bad") is None


def test_cached_release_is_offered_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(updates.paths, "CACHE", tmp_path)
    updates.paths.private_json(
        tmp_path / "update-check.json", {"checked": updates.time.time(), "tag": "v99.0.0"}
    )
    monkeypatch.setattr(updates.httpx, "Client", lambda **kw: pytest.fail("network not needed"))
    assert updates.available() == "v99.0.0"


def test_offline_check_never_prevents_startup(tmp_path, monkeypatch):
    monkeypatch.setattr(updates.paths, "CACHE", tmp_path)

    def offline(**kw):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(updates.httpx, "Client", offline)
    assert updates.available() is None


@pytest.mark.parametrize("answer", ["n", "no", "", "нет"])
def test_decline_does_not_download_or_install(monkeypatch, answer):
    monkeypatch.setattr(updates, "available", lambda **kw: "v99.0.0")
    monkeypatch.setattr("builtins.input", lambda _: answer)
    monkeypatch.setattr(updates, "install", lambda tag: pytest.fail("declined"))
    assert updates.offer(force=True) is False


def test_yes_installs_the_exact_offered_release(monkeypatch):
    installed = []
    monkeypatch.setattr(updates, "available", lambda **kw: "v99.0.0")
    monkeypatch.setattr("builtins.input", lambda _: "yes")
    monkeypatch.setattr(updates, "install", installed.append)
    assert updates.offer(force=True)
    assert installed == ["v99.0.0"]


def test_mismatched_installer_is_never_executed(monkeypatch):
    class Client:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            payload = b"unexpected code"
            return SimpleNamespace(
                content=payload,
                text=hashlib.sha256(b"expected code").hexdigest() + "  install.sh\n",
                raise_for_status=lambda: None,
            )

    monkeypatch.setattr(updates.os, "name", "posix")
    monkeypatch.setattr(updates.httpx, "Client", Client)
    monkeypatch.setattr(updates.subprocess, "run", lambda *a, **kw: pytest.fail("must not execute"))
    with pytest.raises(RuntimeError, match="checksum"):
        updates.install("v99.0.0")


def test_confirmed_install_is_verified_and_pinned_to_offered_version(tmp_path, monkeypatch):
    payload = b"verified installer"
    name = "install.ps1" if updates.os.name == "nt" else "install.sh"
    calls = []

    class Client:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            assert "/releases/download/v99.0.0/" in url
            return SimpleNamespace(
                content=payload,
                text=hashlib.sha256(payload).hexdigest() + "  " + name + "\n",
                raise_for_status=lambda: None,
            )

    stage = tmp_path / "stage"
    stage.mkdir()
    monkeypatch.setattr(updates.tempfile, "mkdtemp", lambda **kw: str(stage))
    monkeypatch.setattr(updates.httpx, "Client", Client)
    monkeypatch.setattr(updates.subprocess, "run", lambda args, **kw: calls.append((args, kw)))
    monkeypatch.setattr(updates.subprocess, "Popen", lambda args, **kw: calls.append((args, kw)))
    updates.install("v99.0.0")
    assert len(calls) == 1
    args, options = calls[0]
    assert options["env"]["TSPOTIFY_RELEASE"] == "v99.0.0"
    if updates.os.name == "nt":
        assert args[:3] == ["powershell.exe", "-NoProfile", "-Command"]
        assert "Wait-Process" in args[3]
        assert str(stage / name) in args[3]
    else:
        assert args == ["sh", str(stage / name)]
        assert not stage.exists()
