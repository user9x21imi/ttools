"""Opt-in release updates. Never run downloaded code without a confirmation."""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

from . import __version__, paths

REPO = "https://github.com/user9x21imi/tspotify"
API = "https://api.github.com/repos/user9x21imi/tspotify/releases/latest"


def version(value):
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value)
    return tuple(map(int, match.groups())) if match else None


def available(force=False):
    """Check at most daily; network failures never prevent opening the player."""
    state = paths.CACHE / "update-check.json"
    try:
        saved = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    checked = saved.get("checked", 0)
    if not isinstance(checked, (int, float)):
        checked = 0
    if not force and time.time() - checked < 86400:
        tag = saved.get("tag", "")
    else:
        try:
            with httpx.Client(timeout=3, follow_redirects=True) as client:
                response = client.get(API, headers={"Accept": "application/vnd.github+json"})
                response.raise_for_status()
                release = response.json()
                tag = release.get("tag_name", "")
                if release.get("prerelease") or release.get("draft") or not version(tag):
                    return None
            paths.private_json(state, {"checked": time.time(), "tag": tag})
        except (httpx.HTTPError, OSError, ValueError, TypeError):
            return None
    return tag if isinstance(tag, str) and version(tag) and version(tag) > version(__version__) else None


def install(tag):
    """Fetch a pinned release installer and validate its published checksum."""
    from .managed import owner

    if owner() == "ttools":
        raise RuntimeError("Эта установка обновляется через ttools")
    if not version(tag):
        raise ValueError("Invalid release version")
    name = "install.ps1" if os.name == "nt" else "install.sh"
    base = f"{REPO}/releases/download/{tag}"
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        manifest = client.get(base + "/SHA256SUMS.txt")
        manifest.raise_for_status()
        payload = client.get(base + "/" + name)
        payload.raise_for_status()
    expected = [line.split()[0] for line in manifest.text.splitlines() if line.split()[1:] == [name]]
    if expected != [hashlib.sha256(payload.content).hexdigest()]:
        raise RuntimeError("Update checksum mismatch; installation stopped")
    directory = Path(tempfile.mkdtemp(prefix="tspotify-update-"))
    script = directory / name
    script.write_bytes(payload.content)
    # Pin the archive to the same release as the verified installer.
    env = dict(os.environ, TSPOTIFY_RELEASE=tag)
    if os.name == "nt":
        # Windows locks running executables. A separate PowerShell waits for us
        # to exit before replacing the app; no execution-policy bypass is used.
        quoted_script = str(script).replace("'", "''")
        quoted_directory = str(directory).replace("'", "''")
        command = (
            f"Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue; "
            f"$env:TSPOTIFY_RELEASE = '{tag}'; "
            f"try {{ & ([scriptblock]::Create([IO.File]::ReadAllText('{quoted_script}'))) }} "
            "catch { Write-Error $_ -ErrorAction Continue; Read-Host 'Press Enter' } "
            f"finally {{ Remove-Item -Recurse -Force '{quoted_directory}' -ErrorAction SilentlyContinue }}"
        )
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-Command", command],
            env=env,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    else:
        try:
            subprocess.run(["sh", str(script)], env=env, check=True)
        finally:
            script.unlink(missing_ok=True)
            directory.rmdir()
    print("Update started. Run tspotify again after installation finishes.")


def offer(force=False):
    from .managed import owner

    if owner() == "ttools":
        if force:
            print("Обновления этой установки выполняет ttools.")
        return False
    if not force and (not getattr(sys, "frozen", False) or not sys.stdin.isatty()):
        return False
    tag = available(force=force)
    if not tag:
        if force:
            print("No newer release found, or the update server is unavailable.")
        return False
    print(f"\n+-- tspotify: update {__version__} -> {tag} --+")
    print(f"Release: {REPO}/releases/tag/{tag}")
    try:
        answer = input("Install update? [y/N]: ").strip().lower()
    except EOFError:
        return False
    if answer not in ("y", "yes", "д", "да"):
        return False
    install(tag)
    return True
