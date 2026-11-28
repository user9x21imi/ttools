"""Decode audio in FFmpeg and play its PCM through an isolated SDL device."""
from array import array
from ctypes import (CDLL, POINTER, Structure, byref, c_char_p, c_int, c_uint8,
                    c_uint16, c_uint32, c_void_p)
from ctypes.util import find_library
import cmath
import math
import os
from queue import Empty, Full, Queue
import shutil
import subprocess
import sys
import threading
import time


RATE = 48000
FRAME = 4
CHUNK = 1024


class Spec(Structure):
    _fields_ = [
        ("freq", c_int), ("format", c_uint16), ("channels", c_uint8),
        ("silence", c_uint8), ("samples", c_uint16), ("padding", c_uint16),
        ("size", c_uint32), ("callback", c_void_p), ("userdata", c_void_p),
    ]


class Device:
    def __init__(self):
        library = os.getenv("TSOUND_SDL2") or find_library("SDL2-2.0") or find_library("SDL2")
        if not library and sys.platform == "win32":
            library = "SDL2.dll"
        if not library:
            raise RuntimeError("Нужна библиотека SDL2")
        self.lib = CDLL(library)
        signatures = {
            "SDL_InitSubSystem": (c_int, [c_uint32]),
            "SDL_QuitSubSystem": (None, [c_uint32]),
            "SDL_OpenAudioDevice": (c_uint32, [c_char_p, c_int, POINTER(Spec), POINTER(Spec), c_int]),
            "SDL_CloseAudioDevice": (None, [c_uint32]),
            "SDL_PauseAudioDevice": (None, [c_uint32, c_int]),
            "SDL_GetQueuedAudioSize": (c_uint32, [c_uint32]),
            "SDL_QueueAudio": (c_int, [c_uint32, c_char_p, c_uint32]),
            "SDL_GetError": (c_char_p, []),
        }
        for name, (result, args) in signatures.items():
            function = getattr(self.lib, name)
            function.restype, function.argtypes = result, args
        if self.lib.SDL_InitSubSystem(16):
            raise RuntimeError(self.error())
        spec = Spec(freq=RATE, format=0x8010, channels=2, samples=512)
        self.id = self.lib.SDL_OpenAudioDevice(None, 0, byref(spec), None, 0)
        if not self.id:
            self.lib.SDL_QuitSubSystem(16)
            raise RuntimeError(self.error())

    def error(self):
        return self.lib.SDL_GetError().decode(errors="replace")

    def queued(self):
        return self.lib.SDL_GetQueuedAudioSize(self.id)

    def send(self, data):
        if self.lib.SDL_QueueAudio(self.id, data, len(data)):
            raise RuntimeError(self.error())

    def pause(self, paused):
        self.lib.SDL_PauseAudioDevice(self.id, paused)

    def close(self):
        self.lib.SDL_CloseAudioDevice(self.id)
        self.lib.SDL_QuitSubSystem(16)


def fft(samples):
    if len(samples) <= 1:
        return samples
    even, odd = fft(samples[::2]), fft(samples[1::2])
    n = len(samples)
    angles = [cmath.exp(-2j * math.pi * k / n) * value for k, value in enumerate(odd)]
    return [a + b for a, b in zip(even, angles)] + [a - b for a, b in zip(even, angles)]


WINDOW = [0.5 - 0.5 * math.cos(2 * math.pi * i / 255) for i in range(256)]
BANDS = (1, 2, 3, 4, 6, 8, 11, 15, 20, 27, 36, 48, 64, 84, 108, 128)


def spectrum(pcm):
    bins = fft([pcm[i * 4] / 32768 * WINDOW[i] for i in range(256)])
    return [min(1, (max(map(abs, bins[a:b])) / 18) ** .55)
            for a, b in zip(BANDS, BANDS[1:])]


class Playback:
    def __init__(self, url, offset, paused, gain, previous=None):
        self.url = url
        self.offset = self.position = offset
        self.paused = paused
        self.gain = gain
        self.levels = []
        self.label = "Загрузка аудио…"
        self.ended = False
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.process = None
        self.thread = threading.Thread(target=self.run, args=(previous,), daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.kill()

    def read_pcm(self, chunks):
        while not self.stop.is_set():
            data = self.process.stdout.read(CHUNK * FRAME)
            while not self.stop.is_set():
                try:
                    chunks.put(data, timeout=.05)
                    break
                except Full:
                    continue
            if not data:
                break

    def run(self, previous):
        if previous:
            previous.thread.join()
        if self.stop.is_set():
            return
        if not (binary := shutil.which("ffmpeg")):
            self.label = "Нужен FFmpeg"
            return
        device = reader = None
        try:
            with self.lock:
                if self.stop.is_set():
                    return
                self.process = subprocess.Popen(
                    [binary, "-nostdin", "-loglevel", "error", "-rw_timeout", "8000000",
                     "-ss", str(self.offset), "-i", self.url, "-vn", "-ac", "2", "-ar", str(RATE),
                     "-f", "s16le", "pipe:1"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                )
            device = Device()
            chunks = Queue(maxsize=4)
            reader = threading.Thread(target=self.read_pcm, args=(chunks,), daemon=True)
            reader.start()
            written = 0
            eof = False
            next_fft = 0
            while not self.stop.is_set():
                queued = device.queued()
                self.position = self.offset + (written - queued) / (RATE * FRAME)
                device.pause(self.paused)
                if written:
                    self.label = "Пауза" if self.paused else ("Играет" if queued else "Буферизация…")
                if eof and queued == 0:
                    break
                if not eof and queued < CHUNK * FRAME * 2 and (not self.paused or not written):
                    try:
                        data = chunks.get(timeout=.012)
                    except Empty:
                        continue
                    if self.stop.is_set():
                        break
                    if not data:
                        eof = True
                        continue
                    pcm = array("h", data)
                    if sys.byteorder == "big":
                        pcm.byteswap()
                    gain = self.gain
                    if gain != 1:
                        pcm = array("h", (int(value * gain) for value in pcm))
                    now = time.monotonic()
                    if now >= next_fft and len(pcm) >= 1024:
                        self.levels = spectrum(pcm)
                        next_fft = now + .05
                    if sys.byteorder == "big":
                        pcm.byteswap()
                    device.send(pcm.tobytes())
                    written += len(data)
                else:
                    time.sleep(.006)
            if not self.stop.is_set():
                if written and self.process.wait() == 0:
                    self.label = "Трек завершён"
                    self.ended = True
                else:
                    self.label = "Не удалось декодировать поток"
        except (OSError, RuntimeError) as error:
            self.label = str(error)
        finally:
            self.close()
            if self.process:
                self.process.wait()
                if reader:
                    reader.join()
                self.process.stdout.close()
            if device:
                device.close()
