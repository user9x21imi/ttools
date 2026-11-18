import pytest

from tspotify import cli


def test_doctor_does_not_print_credentials(capsys, monkeypatch):
    monkeypatch.setattr(cli, "engine_path", lambda install=False: None)
    cli.main(["doctor"])
    output = capsys.readouterr().out
    assert "Version:" in output and "Login:" in output
    assert "access_token" not in output


def test_engine_is_stopped_when_frontend_initialization_fails(monkeypatch):
    calls = []

    class API:
        external = False

        def select_device(self, *args):
            return None

        def control(self, *args):
            return "paused"

        def close(self):
            calls.append("api-close")

    class Engine:
        def __init__(self, **kwargs):
            calls.append(("engine", kwargs["muted"]))

        def start(self):
            calls.append("start")

        def close(self):
            calls.append("engine-close")

    monkeypatch.setattr(cli.auth, "access_token", lambda: "fake")
    monkeypatch.setattr(cli, "Spotify", API)
    monkeypatch.setattr(cli, "Backend", Engine)
    import curses

    def failure(*args):
        raise RuntimeError("fake display unavailable")

    monkeypatch.setattr(curses, "wrapper", failure)
    with pytest.raises(SystemExit) as error:
        cli.main(["--muted", "--device", "integrated"])
    assert error.value.code == 1
    assert ("engine", True) in calls and calls[-2:] == ["engine-close", "api-close"]


def test_existing_desktop_device_does_not_start_an_integrated_audio_engine(monkeypatch):
    calls = []

    class API:
        external = True
        backend = None

        def select_device(self, *args):
            return {"name": "Desktop Spotify"}

        def close(self):
            calls.append("closed")

    monkeypatch.setattr(cli.auth, "access_token", lambda: "fake")
    monkeypatch.setattr(cli, "Spotify", API)
    monkeypatch.setattr(cli, "Backend", lambda **kwargs: pytest.fail("must not start another player"))
    import curses

    monkeypatch.setattr(curses, "wrapper", lambda fn: None)
    cli.main(["--no-splash"])
    assert calls == ["closed"]
