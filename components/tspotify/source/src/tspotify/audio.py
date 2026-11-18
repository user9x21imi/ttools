"""Spotify-only FFT capture. Never fall back to the mixed system output."""

import json
import os
import platform
import select
import shutil
import subprocess
import threading
import time

import numpy as np


def spotify_capture_target():
    """Resolve a specific Spotify sink input and the monitor of its own sink."""
    env = dict(os.environ, LC_ALL="C.UTF-8")
    streams = json.loads(
        subprocess.check_output(
            ["pactl", "--format=json", "list", "sink-inputs"],
            timeout=3,
            env=env,
            stderr=subprocess.DEVNULL,
        )
    )
    candidates = []
    for stream in streams:
        props = stream.get("properties", {})
        if (
            props.get("application.process.binary", "").rsplit("/", 1)[-1] == "spotify_player"
            or props.get("node.name") == "alsa_playback.spotify_player"
            or props.get("application.name") == "PipeWire ALSA [spotify_player]"
        ):
            candidates.append(stream)
    if not candidates:
        return None
    stream = max(candidates, key=lambda item: item["index"])
    sinks = json.loads(
        subprocess.check_output(
            ["pactl", "--format=json", "list", "sinks"],
            timeout=3,
            env=env,
            stderr=subprocess.DEVNULL,
        )
    )
    sink = next((item for item in sinks if item["index"] == stream.get("sink")), None)
    if not sink or not sink.get("name"):
        return None
    return stream["index"], sink["name"] + ".monitor"


class Audio:
    def __init__(self, source=None):
        self.bars = [0.0] * 32
        self.enabled = True
        self.source = source or (lambda: True)
        self.stop = threading.Event()
        self.capture_lock = threading.Lock()
        self.process = None
        self.status = "ожидаю поток Spotify"
        self.n = 2048
        self.window = np.hanning(self.n).astype(np.float32)
        edges = np.geomspace(3, self.n // 2 - 1, 33).astype(int)
        self.bands = [(int(edges[i]), max(int(edges[i]) + 1, int(edges[i + 1]))) for i in range(32)]
        self.thread = threading.Thread(target=self.run, daemon=True, name="tspotify-audio-spectrum")
        self.thread.start()

    def update(self, data):
        if not self.enabled or self.stop.is_set():
            return
        samples = np.asarray(data, dtype=np.float32)
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        if len(samples) != self.n:
            return
        bins = np.abs(np.fft.rfft(samples * self.window)) / self.n
        peaks = np.array([bins[lo:hi].max(initial=0) for lo, hi in self.bands])
        db = 20 * np.log10(np.maximum(peaks, 1e-8))
        self.bars = np.clip((db + 74) / 65, 0, 1).tolist()

    def stop_capture(self):
        with self.capture_lock:
            process, self.process = self.process, None
            if process:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
                if process.stdout:
                    process.stdout.close()
        self.bars = [0.0] * 32

    def capture_linux(self):
        target, checked, buffer = None, 0.0, bytearray()
        while not self.stop.is_set():
            if time.monotonic() >= checked:
                desired = None
                if not self.source():
                    self.status = "внешний Spotify · аудиопоток недоступен"
                elif not self.enabled:
                    self.status = "выключен"
                else:
                    try:
                        desired = spotify_capture_target()
                        self.status = "только Spotify" if desired else "ожидаю поток Spotify"
                    except (OSError, ValueError, subprocess.SubprocessError):
                        self.status = "поток Spotify недоступен"
                if desired != target or (self.process and self.process.poll() is not None):
                    self.stop_capture()
                    target, buffer = desired, bytearray()
                    if target:
                        with self.capture_lock:
                            if self.stop.is_set():
                                return
                            self.process = subprocess.Popen(
                                [
                                    "parec",
                                    "--monitor-stream=" + str(target[0]),
                                    "--device=" + target[1],
                                    "--format=float32le",
                                    "--rate=32000",
                                    "--channels=1",
                                    "--latency-msec=60",
                                ],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,
                            )
                checked = time.monotonic() + 1
            process = self.process
            if not process or process.poll() is not None:
                self.bars = [0.0] * 32
                self.stop.wait(0.2)
                continue
            try:
                readable, _, _ = select.select([process.stdout], [], [], 0.2)
                if not readable:
                    continue
                data = os.read(process.stdout.fileno(), self.n * 4)
                if not data:
                    self.stop_capture()
                    target = None
                    self.stop.wait(0.5)
                    continue
                buffer.extend(data)
                while len(buffer) >= self.n * 4:
                    frame = bytes(buffer[: self.n * 4])
                    del buffer[: self.n * 4]
                    self.update(np.frombuffer(frame, dtype="<f4"))
            except (OSError, ValueError):
                if not self.stop.is_set():
                    self.stop_capture()
                    target = None

    def capture_dedicated_loopback(self):
        # Windows/macOS mixed loopback is deliberately forbidden. An explicitly
        # configured virtual channel must be routed to Spotify alone by the user.
        configured = os.environ.get("TSPOTIFY_SPOTIFY_LOOPBACK")
        if not configured:
            self.status = "нужен отдельный канал Spotify · системный звук не захватывается"
            self.stop.wait()
            return
        import soundcard as sc

        candidates = sc.all_microphones(include_loopback=True)
        device = next((item for item in candidates if configured in (item.name, str(item.id))), None)
        if device is None:
            self.status = "отдельный канал Spotify не найден"
            return
        while not self.stop.is_set():
            if not self.source() or not self.enabled:
                self.bars = [0.0] * 32
                self.status = "ожидаю локальный поток Spotify"
                self.stop.wait(0.5)
                continue
            self.status = "отдельный канал Spotify"
            with device.recorder(samplerate=32000, channels=2, blocksize=self.n) as recorder:
                while not self.stop.is_set() and self.source() and self.enabled:
                    self.update(recorder.record(numframes=self.n))

    def run(self):
        try:
            if platform.system() == "Linux" and shutil.which("parec") and shutil.which("pactl"):
                self.capture_linux()
            else:
                self.capture_dedicated_loopback()
        except (ImportError, OSError, RuntimeError, subprocess.SubprocessError):
            self.status = "захват Spotify недоступен · музыка работает без спектра"
        finally:
            self.stop_capture()

    def close(self):
        self.stop.set()
        self.stop_capture()
        self.thread.join(timeout=3)
