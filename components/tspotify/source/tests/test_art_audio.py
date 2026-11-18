import io

import httpx
import numpy as np
import pytest
from PIL import Image

from tspotify import art
from tspotify.audio import Audio


@pytest.mark.parametrize(
    "url,allowed",
    [
        ("https://i.scdn.co/image/a", True),
        ("https://image-cdn-fa.spotifycdn.com/image/a", True),
        ("https://mosaic.scdn.co/abc", True),
        ("http://127.0.0.1/secret", False),
        ("https://scdn.co.attacker.example/a", False),
        ("file:///etc/passwd", False),
    ],
)
def test_cover_source_validation(url, allowed):
    assert art.allowed_image(url) is allowed


def test_cover_is_resized_and_downloaded_once(monkeypatch):
    output = io.BytesIO()
    Image.new("RGB", (12, 12), (255, 80, 20)).save(output, "PNG")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=output.getvalue())

    monkeypatch.setattr(art, "_http", httpx.Client(transport=httpx.MockTransport(handler)))
    art.cover.cache_clear()
    image = art.cover("https://i.scdn.co/image/test", 24, 24)
    assert len(image) == 24 and len(image[0]) == 24
    assert art.cover("https://i.scdn.co/image/test", 24, 24) is image
    assert len(calls) == 1


def test_logo_is_a_symmetric_circle_with_three_dark_arcs():
    image = art.logo()
    assert len(image) == 80 and len(image[0]) == 80
    assert image[0][0] == (0, 0, 0)
    center = [sum(image[y][40]) > 100 for y in range(80)]
    dark_runs = sum(not center[i] and center[i - 1] for i in range(1, 78))
    assert dark_runs >= 3


def test_real_fft_distinguishes_silence_and_a_low_frequency_tone():
    audio = Audio.__new__(Audio)
    import threading

    audio.enabled = True
    audio.stop = threading.Event()
    audio.n = 2048
    audio.window = np.hanning(audio.n).astype(np.float32)
    edges = np.geomspace(3, audio.n // 2 - 1, 33).astype(int)
    audio.bands = [(int(edges[i]), max(int(edges[i]) + 1, int(edges[i + 1]))) for i in range(32)]
    audio.update(np.zeros(audio.n, dtype=np.float32))
    assert max(audio.bars) == 0
    audio.update(0.6 * np.sin(2 * np.pi * 250 * np.arange(audio.n) / 32000))
    assert max(audio.bars) > 0.6
    assert np.argmax(audio.bars) < 16


def test_spotify_capture_selects_only_the_matching_stream_and_its_sink(monkeypatch):
    import json
    from tspotify import audio

    calls = []
    streams = [
        {"index": 10, "sink": 7, "properties": {"application.name": "Notifications"}},
        {"index": 11, "sink": 8, "properties": {"application.name": "PipeWire ALSA [spotify_player]"}},
        {"index": 12, "sink": 7, "properties": {"application.name": "Zen"}},
    ]

    def response(args, **kwargs):
        calls.append(args)
        return json.dumps(
            streams
            if args[-1] == "sink-inputs"
            else [{"index": 7, "name": "system"}, {"index": 8, "name": "headphones"}]
        ).encode()

    monkeypatch.setattr(audio.subprocess, "check_output", response)
    assert audio.spotify_capture_target() == (11, "headphones.monitor")
    assert all("get-default-sink" not in args for args in calls)


def test_absent_spotify_stream_never_falls_back_to_system_monitor(monkeypatch):
    import json
    from tspotify import audio

    monkeypatch.setattr(
        audio.subprocess,
        "check_output",
        lambda *a, **kw: json.dumps(
            [
                {"index": 99, "sink": 1, "properties": {"application.name": "Browser"}},
            ]
        ).encode(),
    )
    assert audio.spotify_capture_target() is None


def test_remote_connect_does_not_capture_any_local_audio(monkeypatch):
    import time
    from tspotify import audio

    monkeypatch.setattr(audio.platform, "system", lambda: "Linux")
    monkeypatch.setattr(audio.shutil, "which", lambda _: "/fake")
    monkeypatch.setattr(
        audio,
        "spotify_capture_target",
        lambda: pytest.fail("No local audio may be captured for a remote device"),
    )
    capture = audio.Audio(source=lambda: False)
    try:
        deadline = time.monotonic() + 1
        while "внешний" not in capture.status and time.monotonic() < deadline:
            time.sleep(0.01)
        assert "внешний" in capture.status
        assert capture.process is None and max(capture.bars) == 0
    finally:
        capture.close()
    assert not capture.thread.is_alive()


@pytest.mark.parametrize("system", ["Windows", "Darwin"])
def test_windows_and_mac_never_use_a_default_system_loopback(monkeypatch, system):
    import time
    from tspotify import audio

    monkeypatch.setattr(audio.platform, "system", lambda: system)
    monkeypatch.delenv("TSPOTIFY_SPOTIFY_LOOPBACK", raising=False)
    capture = audio.Audio()
    try:
        deadline = time.monotonic() + 1
        while "нужен отдельный" not in capture.status and time.monotonic() < deadline:
            time.sleep(0.01)
        assert "нужен отдельный канал Spotify" in capture.status
        assert max(capture.bars) == 0 and capture.process is None
    finally:
        capture.close()
    assert not capture.thread.is_alive()


def test_cover_uses_a_sufficient_resolution_without_downloading_the_largest_image():
    images = [{"url": "big", "width": 640}, {"url": "medium", "width": 300}, {"url": "thumb", "width": 64}]
    assert art.image_url(images, 256) == "medium"
    assert art.image_url(images, 24) == "thumb"
    assert art.image_url(images, 900) == "big"
