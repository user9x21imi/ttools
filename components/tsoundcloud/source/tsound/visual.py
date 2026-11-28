from bisect import bisect_right
from functools import lru_cache
import math
import re
import shutil
import subprocess
import time

from .service import cdn_bytes


def clock(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


@lru_cache(maxsize=64)
def _wave_columns(samples, width):
    count = len(samples)
    result = []
    for index in range(width):
        start = index * count // width
        stop = max(start + 1, (index + 1) * count // width)
        group = samples[start:stop]
        rms = math.sqrt(sum(value * value for value in group) / len(group))
        result.append(.2 * max(group) + .8 * rms)
    return result


def peaks(samples, width):
    return _wave_columns(tuple(samples), width) if samples and width > 0 else []


def column(seconds, duration, width):
    if duration <= 0:
        return 0
    return min(width - 1, max(0, round(seconds / duration * (width - 1))))


class Timeline:
    def __init__(self):
        self.comments = []
        self.times = []
        self.position = -0.001
        self.visible = []
        self.until = 0

    def set_comments(self, comments):
        self.comments = sorted(c for c in comments if math.isfinite(c.seconds) and c.seconds >= 0)
        self.times = [comment.seconds for comment in self.comments]

    def reset(self, position):
        self.position = position - .001
        self.visible = []
        self.until = 0

    def advance(self, position, playing, now=None):
        now = time.monotonic() if now is None else now
        if playing:
            first = bisect_right(self.times, self.position)
            last = bisect_right(self.times, position)
            if last > first:
                self.visible = self.comments[first:last][-3:]
                self.until = now + 4
            self.position = position
        return self.visible if self.until > now else []


ART_SIZE = 192


def image_bytes(binary, data, width, height, pixel_format):
    result = subprocess.run([binary, "-nostdin", "-loglevel", "error", "-i", "pipe:0",
                             "-vf", f"scale={width}:{height}:flags=lanczos",
                             "-frames:v", "1", "-pix_fmt", pixel_format,
                             "-f", "rawvideo", "pipe:1"],
                            input=data, capture_output=True, timeout=6)
    return result.stdout if result.returncode == 0 else b""


def png_waveform(data):
    binary = shutil.which("ffmpeg")
    if not binary:
        return []
    width, height = 1024, 96
    pixels = image_bytes(binary, data, width, height, "rgba")
    if len(pixels) != width * height * 4:
        return []
    bounds = (pixels[:4], pixels[(width - 1) * 4:width * 4], pixels[-4:])
    background = min(bounds, key=lambda point: sum(
        sum(abs(a - b) for a, b in zip(point, other)) for other in bounds))
    samples = [0] * width
    for row in range(height):
        for col in range(width):
            offset = (row * width + col) * 4
            color = pixels[offset:offset + 4]
            if (abs(color[3] - background[3]) > 40 or
                    (color[3] > 64 and background[3] > 64 and
                     sum(abs(a - b) for a, b in zip(color[:3], background[:3])) > 130)):
                samples[col] += 1
    maximum = max(samples, default=0)
    return [sample / maximum for sample in samples] if len(set(samples)) > 1 and maximum else []


@lru_cache(maxsize=32)
def pixels(url):
    binary = shutil.which("ffmpeg")
    if not binary:
        return b""
    highres = re.sub(r"-(?:large|badge|small|t\d+x\d+)(?=\.(?:jpg|png)(?:\?|$))",
                     "-t500x500", url)
    for address in dict.fromkeys((highres, url)):
        try:
            data = cdn_bytes(address, 3_000_000, ("sndcdn.com",))
        except OSError:
            continue
        if data:
            result = image_bytes(binary, data, ART_SIZE, ART_SIZE, "rgb24")
            if len(result) == ART_SIZE * ART_SIZE * 3:
                return result
    return b""


def demo_pixels(seed):
    return bytes(channel for y in range(64) for x in range(64)
                 for channel in demo_color(x, y, seed))


def demo_color(x, y, seed):
    arch = ((x - 31) ** 2 + (y - 33) ** 2) ** .5
    if 14 < arch < 27 and (x + y + seed) % 13 > 2:
        return 255, 130 + (x * 3 + seed) % 110, 50
    if y > 35 and (x * 5 + seed) % 29 > y - 36:
        return 110, 72, 180
    return 14 + x, 22 + y // 2, 55 + (x + seed) % 45


@lru_cache(maxsize=128)
def dots(data, width, height, ascii_mode, crop=False):
    order = (0, 3, 1, 4, 2, 5, 6, 7)
    thresholds = (15, 105, 155, 57, 36, 133, 186, 78)
    if not data:
        return []
    side = math.isqrt(len(data) // 3)
    ratio = width / (2.1 * height) if crop else 1
    source_w = max(1, round(side * min(1, ratio)))
    source_h = max(1, round(side / max(1, ratio)))
    left, top = (side - source_w) // 2, (side - source_h) // 2
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            values = []
            for index in range(8):
                sample_x = left + (2 * x + index % 2) * source_w // (2 * width)
                sample_y = top + (4 * y + index // 2) * source_h // (4 * height)
                offset = (side * sample_y + sample_x) * 3
                values.append(data[offset:offset + 3])
            rgb = tuple(min(255, round((sum(pixel[i] for pixel in values) / 2040) ** .7 * 255))
                        for i in range(3))
            mask = sum(1 << order[i] for i, color in enumerate(values) if max(color) > thresholds[i])
            glyph = " .:-=+*#@"[mask.bit_count()] if ascii_mode else chr(0x2800 + mask)
            row.append((glyph, rgb))
        rows.append(row)
    return rows


def decoded_waveform(url, duration, cancelled):
    """Build peaks from playable audio when track metadata has no waveform."""
    from array import array
    import sys

    binary = shutil.which("ffmpeg")
    if not binary or not 0 < duration <= 7200 or cancelled.is_set():
        return []
    sample_rate = 8000
    frames = max(1, round(duration * sample_rate / 1800))
    peaks = []
    command = [binary, "-nostdin", "-loglevel", "error", "-rw_timeout", "8000000",
               "-i", url, "-vn", "-t", str(duration + 1), "-ac", "1", "-ar", str(sample_rate),
               "-f", "s16le", "pipe:1"]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
        from threading import Thread
        finished = type(cancelled)()

        def watch():
            deadline = time.monotonic() + 90
            while not finished.wait(.1):
                if cancelled.is_set() or time.monotonic() >= deadline:
                    if process.poll() is None:
                        process.kill()
                    break

        watcher = Thread(target=watch, daemon=True)
        watcher.start()
        try:
            while not cancelled.is_set():
                data = process.stdout.read(frames * 2)
                if not data:
                    break
                samples = array("h", data)
                if sys.byteorder == "big":
                    samples.byteswap()
                peaks.append(math.sqrt(sum(sample * sample for sample in samples) / len(samples)))
        finally:
            if process.poll() is None and cancelled.is_set():
                process.kill()
            status = process.wait()
            finished.set()
            watcher.join()
    if status or len(peaks) * frames < duration * sample_rate * .95:
        return []
    peak = max(peaks, default=0)
    return [value / peak for value in peaks] if peak else []
