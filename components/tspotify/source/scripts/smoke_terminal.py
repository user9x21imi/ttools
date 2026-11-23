"""Exercise a real native curses frontend in an offline pseudo-terminal."""

import os
import importlib.util
import subprocess
import sys
import threading
import time
from pathlib import Path

arguments = sys.argv[1:]
source_mode = "--source" in arguments
binary_arg = next((arg for arg in arguments if not arg.startswith("--")), None)
if source_mode and binary_arg:
    raise SystemExit("Pass either --source or a native binary path, not both")
if source_mode:
    source = Path(__file__).resolve().parents[1] / "src"
    missing = [name for name in ("PIL", "numpy", "qrcode", "platformdirs", "httpx") if importlib.util.find_spec(name) is None]
    if missing:
        packages = {"PIL": "Pillow"}
        names = ", ".join(packages.get(name, name) for name in missing)
        raise SystemExit(f"Missing tspotify dependencies: {names}. Set up the project with `python -m pip install -e '.[dev]'`.")
    os.environ["PYTHONPATH"] = str(source) + os.pathsep + os.environ.get("PYTHONPATH", "")
    command = [
        sys.executable,
        "-c",
        f"import sys; sys.path.insert(0, {str(source)!r}); from tspotify.cli import main; main(['--demo', '--no-splash', '--no-motion'])",
    ]
else:
    if binary_arg is None:
        raise SystemExit("Usage: smoke_terminal.py --source [options] | smoke_terminal.py BINARY [options]")
    command = [str(Path(binary_arg).resolve()), "--demo", "--no-splash", "--no-motion"]
height, width = (24, 80) if "--compact" in arguments else (48, 140)
output = []
seen = threading.Event()
quit_key = "\x11" if "--ctrl-q" in sys.argv else "q"


def interact(send):
    if "--interact" not in sys.argv:
        return
    def wait_for(marker, start=0):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if marker in "".join(output)[start:]:
                return
            time.sleep(0.025)
        raise RuntimeError(f"F3 smoke did not observe {marker!r}: {''.join(output)[-2000:]}")

    wait_for("F3 PLAYER")
    cursor = len("".join(output))
    send("\x1bOR")  # F3 enters Player Mode.
    wait_for("F3 EXIT", cursor)
    cursor = len("".join(output))
    send("\x1bOR")  # F3 returns to the library.
    wait_for("F3 PLAYER", cursor)


if os.name == "nt":
    from winpty import PtyProcess

    process = PtyProcess.spawn(subprocess.list2cmdline(command), dimensions=(height, width))

    def read():
        while process.isalive():
            try:
                text = process.read(8192)
            except EOFError:
                return
            output.append(text)
            if "DEMO / NO AUDIO" in "".join(output):
                seen.set()

    threading.Thread(target=read, daemon=True).start()
    if not seen.wait(20):
        process.close(force=True)
        raise SystemExit("Native terminal failed to render: " + "".join(output)[-2000:])
    interact(process.write)
    process.write(quit_key)
    deadline = time.monotonic() + 10
    while process.isalive() and time.monotonic() < deadline:
        time.sleep(0.1)
    if process.isalive():
        process.close(force=True)
        raise SystemExit("Native terminal did not exit after the requested shortcut")
else:
    import fcntl
    import pty
    import struct
    import termios

    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", height, width, 0, 0))
    env = dict(os.environ, TERM="xterm-256color")
    process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, env=env)
    os.close(slave)

    def read():
        while process.poll() is None:
            try:
                data = os.read(master, 8192)
            except OSError:
                return
            if not data:
                return
            output.append(data.decode(errors="replace"))
            if b"\x1b[6n" in data:
                os.write(master, b"\x1b[1;1R")
            if "DEMO / NO AUDIO" in "".join(output):
                seen.set()

    threading.Thread(target=read, daemon=True).start()
    if not seen.wait(20):
        process.kill()
        process.wait()
        raise SystemExit("Native terminal failed to render: " + "".join(output)[-2000:])
    interact(lambda value: os.write(master, value.encode()))
    os.write(master, quit_key.encode())
    try:
        code = process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise SystemExit("Native terminal did not exit after the requested shortcut") from None
    os.close(master)
    if code:
        raise SystemExit("Native terminal returned an error: " + "".join(output)[-2000:])

shortcut = "Ctrl+Q" if quit_key == "\x11" else "q"
mode = "source demo" if source_mode else "Native terminal"
print(f"{mode} rendered dotted UI and exited with {shortcut}; no account or audio used.")
if "--interact" in arguments:
    print("F3 entered Player Mode and returned to the library.")
