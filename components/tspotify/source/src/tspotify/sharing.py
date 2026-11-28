"""Public Spotify links and optional system clipboard; no credentials or API calls."""

import os
import re
import shutil
import subprocess
import sys


def share_url(item):
    uri = item.get("uri", "")
    match = re.fullmatch(r"spotify:(track|album|playlist|artist|episode|show):([A-Za-z0-9]+)", uri)
    if match:
        return f"https://open.spotify.com/{match[1]}/{match[2]}"
    kind, identity = item.get("type", "track"), item.get("id", "")
    if kind in ("track", "album", "playlist", "artist", "episode", "show") and re.fullmatch(
        r"[A-Za-z0-9]+", identity
    ):
        return f"https://open.spotify.com/{kind}/{identity}"
    return ""


def copy_link(url):
    candidates = []
    if sys.platform == "darwin":
        candidates.append((["pbcopy"], url))
    elif sys.platform == "win32":
        candidates.append((["clip.exe"], url))
    else:
        if os.environ.get("WAYLAND_DISPLAY"):
            candidates.append((["wl-copy"], url))
        if os.environ.get("DISPLAY"):
            candidates.extend(
                [(["xclip", "-selection", "clipboard"], url), (["xsel", "--clipboard", "--input"], url)]
            )
        for binary in ("qdbus6", "qdbus"):
            candidates.append(
                (
                    [
                        binary,
                        "org.kde.klipper",
                        "/klipper",
                        "org.kde.klipper.klipper.setClipboardContents",
                        url,
                    ],
                    None,
                )
            )
    for argv, stdin in candidates:
        if not shutil.which(argv[0]):
            continue
        try:
            result = subprocess.run(argv, input=stdin, text=True, capture_output=True, timeout=2)
            if result.returncode == 0:
                return "Ссылка скопирована — отправьте её в любом приложении"
        except (OSError, subprocess.TimeoutExpired):
            continue
    return "Буфер обмена недоступен. Скопируйте ссылку ниже выделением в терминале (Shift + мышь)"


def jam_invite_url(url):
    """Turn Spotify's actual internal join URL into its public social-session route."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if (
        parsed.scheme == "hm"
        and parsed.netloc == "social-connect"
        and not parsed.query
        and not parsed.fragment
    ):
        match = re.fullmatch(r"/v2/sessions/join/([A-Za-z0-9_-]{8,512})", parsed.path)
        if match:
            return "https://open.spotify.com/socialsession/" + match[1]
    if (
        parsed.scheme == "https"
        and not parsed.username
        and not parsed.password
        and (
            parsed.hostname in ("spotify.link", "spotify.app.link", "spotify.com", "open.spotify.com")
            or (parsed.hostname or "").endswith(".spotify.link")
        )
    ):
        return url
    raise ValueError("Spotify вернул неизвестный адрес приглашения Jam")
