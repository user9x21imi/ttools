"""Linux-only silent integration check using two streams on an owned null sink."""

import json
import os
import select
import subprocess
import time
import tempfile
from pathlib import Path
import numpy as np
from tspotify import audio


def read_pcm(process, frames):
    data = bytearray()
    deadline = time.monotonic() + 6
    while len(data) < frames * 4 and time.monotonic() < deadline:
        ready, _, _ = select.select([process.stdout], [], [], 0.2)
        if ready:
            chunk = os.read(process.stdout.fileno(), frames * 4 - len(data))
            if not chunk:
                break
            data.extend(chunk)
    assert len(data) == frames * 4, "No PCM from monitor"
    return np.frombuffer(data, dtype="<f4")


os.environ["LC_ALL"] = "C.UTF-8"
name = "tspotify_spectrum_qa_" + str(os.getpid())
module = None
processes = []
capture = None
try:
    module = subprocess.check_output(
        ["pactl", "load-module", "module-null-sink", "sink_name=" + name], text=True, timeout=5
    ).strip()
    with tempfile.TemporaryDirectory(prefix="tspotify-spectrum-") as folder:
        for freq, label in [(500, "target"), (2000, "unrelated")]:
            path = Path(folder) / (label + ".raw")
            t = np.arange(32000 * 14) / 32000
            path.write_bytes((0.3 * np.sin(2 * np.pi * freq * t)).astype("<f4").tobytes())
            processes.append(
                subprocess.Popen(
                    [
                        "paplay",
                        "--raw",
                        "--format=float32le",
                        "--rate=32000",
                        "--channels=1",
                        "--device=" + name,
                        "--property=application.name=tspotify-qa-" + label,
                        str(path),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
            )
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            streams = json.loads(subprocess.check_output(["pactl", "--format=json", "list", "sink-inputs"]))
            selected = next(
                (
                    x
                    for x in streams
                    if x.get("properties", {}).get("application.name") == "tspotify-qa-target"
                ),
                None,
            )
            if selected:
                break
            time.sleep(0.1)
        assert selected, "No test stream"
        baseline = subprocess.Popen(
            ["parec", "--device=" + name + ".monitor", "--format=float32le", "--rate=32000", "--channels=1"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        processes.append(baseline)
        mixed = read_pcm(baseline, 32000)
        baseline.terminate()
        baseline.wait(timeout=3)
        baseline_bins = np.abs(np.fft.rfft(mixed * np.hanning(32000)))
        assert baseline_bins[495:506].max() > 10 and baseline_bins[1995:2006].max() > 10, (
            "Both test tones must exist in the mixed null-sink monitor"
        )
        print("Baseline: both test streams confirmed in the isolated null sink", flush=True)
        capture = subprocess.Popen(
            [
                "parec",
                "--monitor-stream=" + str(selected["index"]),
                "--device=" + name + ".monitor",
                "--format=float32le",
                "--rate=32000",
                "--channels=1",
                "--latency-msec=60",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        pcm = read_pcm(capture, 32000 * 2)
        bins = np.abs(np.fft.rfft(pcm[-32000:] * np.hanning(32000)))
        wanted = float(bins[495:506].max())
        other = float(bins[1995:2006].max())
        print("Target tone 500 Hz:", round(wanted, 3), "Other stream 2000 Hz:", round(other, 3), flush=True)
        assert wanted > 10 and other < wanted * 0.01, "Unrelated audio leaked into stream monitor"
        audio.spotify_capture_target = lambda: (selected["index"], name + ".monitor")
        visualizer = audio.Audio()
        try:
            time.sleep(0.8)
            print(
                "Visualizer status:", visualizer.status, "peak:", round(max(visualizer.bars), 3), flush=True
            )
            assert max(visualizer.bars) > 0.1
        finally:
            visualizer.close()
        print("PASS: simultaneous unrelated audio excluded; test sink has no hardware output", flush=True)
finally:
    if capture:
        capture.terminate()
        capture.wait(timeout=3)
    for process in processes:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=3)
    if module:
        subprocess.run(["pactl", "unload-module", module], check=True, timeout=5)
    print("Removed owned test streams and null sink", flush=True)
