"""Optional KDE global F7-F12 bindings, active only while the client is running."""

import ast
import json
import os
from pathlib import Path
import shutil
import subprocess

from . import paths

COMPONENTS = {
    "previous": (7,),
    "play-pause": (8,),
    "next": (9,),
    "mute": (10,),
    "volume-down": (11,),
    "volume-up": (12,),
}


MEDIA_KEYS = {
    "previous": (0x01000082,),
    "play-pause": (0x01000080, 0x01000085, 0x01000086),
    "next": (0x01000083,),
    "mute": (0x01000071,),
    "volume-down": (0x01000070,),
    "volume-up": (0x01000072,),
}


def array_reply(reply):
    return list(ast.literal_eval(reply.replace("@as ", "").replace("@ai ", ""))[0])


def media_enabled():
    try:
        return json.loads((paths.CONFIG / "global-shortcuts.json").read_text()).get("media_keys", False)
    except (OSError, ValueError):
        return False


def redirect_media_keys():
    backup = paths.CONFIG / "media-key-backup.json"
    saved = json.loads(backup.read_text()) if backup.exists() else []
    codes = {code for keys in MEDIA_KEYS.values() for code in keys}
    owners = {}
    for code in codes:
        identity = array_reply(call("action", str(code)))
        if not identity or identity[0].startswith("tspotify-"):
            continue
        if identity[0] not in ("mediacontrol", "kmix"):
            raise RuntimeError("Медиаклавиша занята пользовательским сочетанием: " + identity[0])
        owners[tuple(identity)] = array_reply(call("shortcut", json.dumps(identity)))
    for identity, keys in owners.items():
        if not any(entry["identity"][:2] == list(identity[:2]) for entry in saved):
            saved.append({"identity": list(identity), "keys": keys})
    # Persist before modifying KDE so a crashed session can restore the defaults.
    paths.private_json(backup, saved)
    for identity, keys in owners.items():
        call(
            "setForeignShortcut", json.dumps(identity), json.dumps([key for key in keys if key not in codes])
        )


def restore_media_keys():
    backup = paths.CONFIG / "media-key-backup.json"
    if not backup.exists():
        return
    saved = json.loads(backup.read_text())
    for entry in saved:
        identity = entry["identity"]
        keys = array_reply(call("shortcut", json.dumps(identity)))
        for code in entry["keys"]:
            if code not in {value for codes in MEDIA_KEYS.values() for value in codes}:
                continue
            owner = array_reply(call("action", str(code)))
            if not owner or owner[:2] == identity[:2]:
                if code not in keys:
                    keys.append(code)
        call("setForeignShortcut", json.dumps(identity), json.dumps(keys))
    backup.unlink()


def call(method, *args):
    result = subprocess.run(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.kde.kglobalaccel",
            "--object-path",
            "/kglobalaccel",
            "--method",
            "org.kde.KGlobalAccel." + method,
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode:
        raise RuntimeError("KDE не принял сочетания клавиш: " + result.stderr[:160])
    return result.stdout


def enabled():
    try:
        return bool(
            json.loads((paths.CONFIG / "global-shortcuts.json").read_text(encoding="utf-8")).get("enabled")
        )
    except (OSError, ValueError, AttributeError):
        return False


def set_active(active):
    try:
        return _set_active(active)
    except (OSError, RuntimeError, ValueError):
        if active and (paths.CONFIG / "media-key-backup.json").exists():
            try:
                _set_active(False)
            except (OSError, RuntimeError, ValueError):
                pass  # Keep the backup for recovery on the next clean shutdown.
        raise


def _set_active(active):
    if not shutil.which("gdbus"):
        return False
    if active:
        for action, functions in COMPONENTS.items():
            component = f"tspotify-{action}.desktop"
            for number in functions:
                code = 0x01000030 + number - 1
                available = "true" in call("isGlobalShortcutAvailable", str(code), component).lower()
                owner = call("action", str(code)) if not available else ""
                owned = (
                    any(f"'tspotify-{name}.desktop'" in owner for name in COMPONENTS) and "'_launch'" in owner
                )
                if not available and not owned:
                    raise RuntimeError(f"F{number} уже используется другим системным сочетанием")
    if active and media_enabled():
        redirect_media_keys()
    if active:
        # Remove our former F7/F9/F11 and F8/F10/F12 volume groups before migration.
        for action in COMPONENTS:
            identity = json.dumps([f"tspotify-{action}.desktop", "_launch", "tspotify", action])
            call("setShortcut", identity, "[]", "6")
    for action, functions in COMPONENTS.items():
        component = f"tspotify-{action}.desktop"
        identity = json.dumps([component, "_launch", "tspotify", action])
        if active:
            call("doRegister", identity)
        keys = [0x01000030 + number - 1 for number in functions] if active else []
        if active and media_enabled():
            keys.extend(MEDIA_KEYS[action])
        # KGlobalAccel: SetPresent=2, NoAutoloading=4. Never steal conflicts.
        call("setShortcut", identity, json.dumps(keys), "6")
    if not active:
        restore_media_keys()
    return True


def install(remove=False):
    if remove:
        set_active(False)
        paths.private_json(paths.CONFIG / "global-shortcuts.json", {"enabled": False})
        return
    if os.name == "nt" or not shutil.which("gdbus"):
        raise RuntimeError(
            "Автоматическая настройка доступна в KDE; для других ОС используйте tspotify control"
        )
    call("isGlobalShortcutAvailable", str(0x01000036), "tspotify-volume-down.desktop")
    executable = shutil.which("tspotify")
    if not executable:
        raise RuntimeError("Команда tspotify должна быть в PATH")
    directory = Path.home() / ".local/share/applications"
    directory.mkdir(parents=True, exist_ok=True)
    for action in COMPONENTS:
        desktop = directory / f"tspotify-{action}.desktop"
        quoted = (
            executable.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("%", "%%")
            .replace("$", "\\$")
            .replace("`", "\\`")
        )
        desktop.write_text(
            "[Desktop Entry]\nType=Application\nName=tspotify "
            + action
            + "\n"
            + f'Exec="{quoted}" control {action}\n'
            + "NoDisplay=true\nTerminal=false\nStartupNotify=false\nX-KDE-GlobalAccel-CommandShortcut=true\n",
            encoding="utf-8",
        )
    builder = shutil.which("kbuildsycoca6")
    if builder:
        subprocess.run(
            [builder], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=True
        )
    paths.private_json(paths.CONFIG / "global-shortcuts.json", {"enabled": True, "media_keys": True})
    # Existing older processes have no control endpoint: register on next startup.
    try:
        from .control import ACTIONS

        endpoint = json.loads((paths.DATA / "control.json").read_text(encoding="utf-8"))
        if endpoint.get("actions") == list(ACTIONS):
            set_active(True)
    except (OSError, ValueError):
        pass
