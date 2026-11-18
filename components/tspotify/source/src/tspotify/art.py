"""Cached dotted artwork. No ffmpeg, native graphics escapes or external fonts required."""

import functools
import hashlib
import io
import json
import threading
import tempfile
from urllib.parse import urlsplit

import httpx
from PIL import Image, ImageDraw

from . import paths

_http = httpx.Client(
    http2=True,
    follow_redirects=True,
    timeout=httpx.Timeout(6, connect=3, pool=2),
    limits=httpx.Limits(max_connections=8, max_keepalive_connections=8),
)
_meta_lock = threading.Lock()


def image_url(images, size=256):
    entries = [entry for entry in images if isinstance(entry, dict) and entry.get("url")]
    if not entries:
        return ""
    measured = [entry for entry in entries if isinstance(entry.get("width"), int) and entry["width"] > 0]
    if not measured:
        return entries[0]["url"]
    adequate = [entry for entry in measured if entry["width"] >= size]
    chosen = (
        min(adequate, key=lambda entry: entry["width"])
        if adequate
        else max(measured, key=lambda entry: entry["width"])
    )
    return chosen["url"]


def allowed_image(url):
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    return parsed.scheme == "https" and (host.endswith(".scdn.co") or host.endswith(".spotifycdn.com"))


@functools.lru_cache(maxsize=16)
def cover(url, width=128, height=128):
    if not allowed_image(url):
        return []
    paths.prepare()
    target = paths.CACHE / ("image-" + hashlib.sha256(url.encode()).hexdigest() + ".bin")
    if target.exists():
        data = target.read_bytes()
    else:
        with _http.stream("GET", url) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes(65536):
                data.extend(chunk)
                if len(data) > 8 * 1024 * 1024:
                    raise RuntimeError("Обложка слишком большая")
        with tempfile.NamedTemporaryFile(
            dir=paths.CACHE, prefix="image-", suffix=".download", delete=False
        ) as stream:
            stream.write(data)
            temporary = stream.name
        from pathlib import Path

        Path(temporary).replace(target)
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
        pixels = list(getattr(image, "get_flattened_data", image.getdata)())
    return [pixels[row * width : (row + 1) * width] for row in range(height)]


def thumbnail(kind, item_id):
    if kind not in ("playlist", "album"):
        return []
    target = paths.CACHE / f"thumbnail-{kind}-{item_id}.json"
    try:
        meta = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        response = _http.get(
            "https://open.spotify.com/oembed",
            params={
                "url": f"https://open.spotify.com/{kind}/{item_id}",
            },
        )
        response.raise_for_status()
        meta = {"url": response.json().get("thumbnail_url", "")}
        with _meta_lock:
            paths.private_json(target, meta)
    return cover(meta["url"], 24, 24) if meta.get("url") else []


@functools.lru_cache(maxsize=1)
def logo():
    # Render at 4x before downsampling for symmetric, smooth dotted arcs.
    image = Image.new("RGB", (512, 512), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((16, 16, 496, 496), fill=(70, 215, 130))
    for center, halfwidth, thickness in [(176, 170, 27), (254, 146, 23), (328, 120, 19)]:
        points = [
            (x, center + 0.0009 * (x - 248) ** 2 + 0.055 * (x - 248))
            for x in range(248 - halfwidth, 248 + halfwidth)
        ]
        draw.line(points, fill=(0, 0, 0), width=thickness)
        r = thickness // 2
        for x, y in (points[0], points[-1]):
            draw.ellipse((x - r, y - r, x + r, y + r), fill=(0, 0, 0))
    image = image.resize((80, 80), Image.Resampling.LANCZOS)
    data = list(getattr(image, "get_flattened_data", image.getdata)())
    return [data[i * 80 : (i + 1) * 80] for i in range(80)]
