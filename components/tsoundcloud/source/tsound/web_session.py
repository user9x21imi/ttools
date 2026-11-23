"""Open SoundCloud and use the session from a selected browser profile."""

from configparser import ConfigParser, Error as ConfigError
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import webbrowser

from . import state


ZEN = "app.zen_browser.zen"
SIGN_IN = "https://soundcloud.com/signin"


def https_handler():
    if mime := shutil.which("xdg-mime"):
        try:
            result = subprocess.run([mime, "query", "default", "x-scheme-handler/https"],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    return ""


def open_default_browser():
    flatpak = shutil.which("flatpak")
    if flatpak and https_handler() == ZEN + ".desktop":
        try:
            browser = subprocess.Popen([flatpak, "run", "--command=launch-script.sh",
                                        ZEN, "--new-window", SIGN_IN],
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
            if browser.wait(timeout=2) == 0:
                return True
        except subprocess.TimeoutExpired:
            return True
        except OSError:
            pass
    for name, arguments in (("kioclient", ["exec"]), ("xdg-open", [])):
        if opener := shutil.which(name):
            try:
                result = subprocess.run([opener, *arguments, SIGN_IN],
                                        capture_output=True, timeout=6)
                if result.returncode == 0:
                    return True
            except (OSError, subprocess.TimeoutExpired):
                continue
    return webbrowser.open(SIGN_IN)


def default_profile():
    handler = https_handler().casefold()
    home = Path.home()
    if "zen" in handler:
        roots = (home / ".var/app/app.zen_browser.zen/.zen", home / ".zen")
    elif "firefox" in handler:
        roots = (home / ".mozilla/firefox", home / ".var/app/org.mozilla.firefox/.mozilla/firefox")
    else:
        return None

    for root in roots:
        config = ConfigParser(interpolation=None)
        try:
            if not config.read(root / "profiles.ini", encoding="utf-8"):
                continue
        except (ConfigError, OSError, UnicodeError):
            continue
        profiles = [config[section] for section in config.sections() if section.startswith("Profile")]
        defaults = {config[section].get("Default") for section in config.sections()
                    if section.startswith("Install")}
        chosen = [profile for profile in profiles if profile.get("Path") in defaults]
        if len(chosen) != 1:
            chosen = [profile for profile in profiles if profile.get("Default") == "1"]
        if not chosen and len(profiles) == 1:
            chosen = profiles
        if len(chosen) == 1 and chosen[0].get("Path"):
            path = Path(chosen[0]["Path"])
            if chosen[0].get("IsRelative") == "1":
                path = root / path
            if path.is_absolute() and path.is_dir():
                return path
    return None


def browser_profile():
    for name in ("zen", "zen-browser", "firefox"):
        if executable := shutil.which(name):
            return [executable], state.directory().absolute() / "soundcloud-browser"
    flatpak = shutil.which("flatpak")
    if flatpak:
        for app in (ZEN, "org.mozilla.firefox"):
            installed = subprocess.run([flatpak, "info", app], capture_output=True, timeout=5)
            if installed.returncode == 0:
                profile = Path.home() / ".var" / "app" / app / "data" / "tsoundcloud-profile"
                return [flatpak, "run", app], profile
    return [], None


def session_token(profile):
    if not profile:
        return None
    jar = profile / "cookies.sqlite"
    if not jar.is_file():
        return None
    for options in ("mode=ro", "mode=ro&immutable=1"):
        try:
            with closing(sqlite3.connect(jar.as_uri() + "?" + options, uri=True, timeout=.1)) as conn:
                row = conn.execute("""
                    SELECT value FROM moz_cookies
                    WHERE host IN ('soundcloud.com', '.soundcloud.com', 'www.soundcloud.com')
                      AND name = 'oauth_token' AND (expiry = 0 OR expiry > ?)
                    ORDER BY lastAccessed DESC LIMIT 1
                    """, (time.time(),)).fetchone()
        except sqlite3.OperationalError as error:
            # Firefox can hold the database exclusively while its profile is open.
            # Reopen a fresh read-only view on every attempt rather than wait for shutdown.
            if "locked" in str(error).lower():
                continue
            return None
        except sqlite3.Error:
            return None
        return row[0] if row and row[0] else None
    return None


def start_browser(command, profile):
    profile.mkdir(mode=0o700, parents=True, exist_ok=True)
    return subprocess.Popen(
        [*command, "--no-remote", "--profile", str(profile), SIGN_IN],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
