import json
import socket

import pytest

from tspotify import control, shortcuts


def test_background_command_reaches_the_running_client_and_closes_cleanly():
    received = []
    server = control.ControlServer(received.append)
    try:
        control.send("volume-up")
        control.send("volume-down")
        assert received == ["volume-up", "volume-down"]
        metadata = json.loads(server.metadata.read_text())
        with socket.create_connection(("127.0.0.1", metadata["port"]), timeout=1) as connection:
            connection.sendall(b'{"action":"volume-up","token":"wrong"}\n')
            assert not json.loads(connection.makefile("rb").readline())["ok"]
        assert len(received) == 2
    finally:
        server.close()
    assert not server.metadata.exists()
    with pytest.raises(RuntimeError, match="не запущен"):
        control.send("volume-up")


def test_background_control_does_not_trigger_browser_login(monkeypatch):
    from tspotify import cli

    received = []
    server = control.ControlServer(received.append)
    monkeypatch.setattr(cli.auth, "access_token", lambda: pytest.fail("control must not log in"))
    try:
        cli.main(["control", "volume-up"])
        assert received == ["volume-up"]
    finally:
        server.close()


def test_global_shortcut_setup_refuses_keys_owned_by_other_programs(monkeypatch):
    calls = []
    monkeypatch.setattr(shortcuts.shutil, "which", lambda _: "/fake/gdbus")

    def call(method, *args):
        calls.append(method)
        return "(false,)" if method == "isGlobalShortcutAvailable" else "(['another.desktop', '_launch'],)"

    monkeypatch.setattr(shortcuts, "call", call)
    with pytest.raises(RuntimeError, match="уже используется"):
        shortcuts.set_active(True)
    assert "setShortcut" not in calls


def test_own_shortcut_registration_can_be_refreshed(monkeypatch):
    monkeypatch.setattr(shortcuts.shutil, "which", lambda _: "/fake/gdbus")

    def call(method, *args):
        if method == "isGlobalShortcutAvailable":
            return "(false,)"
        if method == "action":
            code = int(args[0])
            number = code - 0x01000030 + 1
            action = next(name for name, keys in shortcuts.COMPONENTS.items() if number in keys)
            return f"(['tspotify-{action}.desktop', '_launch'],)"
        return "()"

    monkeypatch.setattr(shortcuts, "call", call)
    assert shortcuts.set_active(True)


def test_desktop_shortcuts_match_the_requested_media_layout():
    assert shortcuts.COMPONENTS == {
        "previous": (7,),
        "play-pause": (8,),
        "next": (9,),
        "mute": (10,),
        "volume-down": (11,),
        "volume-up": (12,),
    }


def test_system_media_bindings_are_restored_without_overwriting_new_user_shortcuts(monkeypatch):
    from tspotify import paths

    identity = ["mediacontrol", "playpausemedia", "Media controller", "Play/pause"]
    media = shortcuts.MEDIA_KEYS["play-pause"][0]
    owners = {media: identity}
    bindings = {tuple(identity): [media, 1234]}
    paths.private_json(paths.CONFIG / "global-shortcuts.json", {"enabled": True, "media_keys": True})

    def call(method, *args):
        if method == "action":
            return repr((owners.get(int(args[0]), []),))
        if method == "shortcut":
            return repr((bindings.get(tuple(json.loads(args[0])), []),))
        if method == "setForeignShortcut":
            key, codes = tuple(json.loads(args[0])), json.loads(args[1])
            bindings[key] = codes
            for code in list(owners):
                if tuple(owners[code]) == key:
                    owners.pop(code)
            owners.update({code: list(key) for code in codes})
        return "()"

    monkeypatch.setattr(shortcuts, "call", call)
    shortcuts.redirect_media_keys()
    assert bindings[tuple(identity)] == [1234]
    shortcuts.restore_media_keys()
    assert set(bindings[tuple(identity)]) == {media, 1234}
    assert not (paths.CONFIG / "media-key-backup.json").exists()
