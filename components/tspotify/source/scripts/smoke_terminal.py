"""Exercise a real native curses frontend in an offline pseudo-terminal."""

import os
import importlib.util
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path

arguments = sys.argv[1:]
source_mode = "--source" in arguments
motion_mode = "--motion" in arguments
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
    demo_flags = ["--demo", "--no-splash"]
    if not motion_mode:
        demo_flags.append("--no-motion")
    command = [
        sys.executable,
        "-c",
        f"import sys; sys.path.insert(0, {str(source)!r}); from tspotify.cli import main; main({demo_flags!r})",
    ]
else:
    if binary_arg is None:
        raise SystemExit("Usage: smoke_terminal.py --source [options] | smoke_terminal.py BINARY [options]")
    command = [str(Path(binary_arg).resolve()), "--demo", "--no-splash"]
    if not motion_mode:
        command.append("--no-motion")
height, width = (24, 80) if "--compact" in arguments else (48, 140)
output = []
seen = threading.Event()
quit_key = "\x11" if "--ctrl-q" in sys.argv else "q"


def screen_text():
    screen = [[" "] * width for _ in range(height)]
    row = col = 0
    text = "".join(output)
    i = 0
    while i < len(text):
        char = text[i]
        if char == "\x1b":
            if i + 1 < len(text) and text[i + 1] == "[":
                end = i + 2
                while end < len(text) and not ("@" <= text[end] <= "~"):
                    end += 1
                if end >= len(text):
                    break
                params, command_name = text[i + 2 : end], text[end]
                values = params.lstrip("?").split(";") if params else []
                numbers = [int(value) if value.isdigit() else 0 for value in values]
                if command_name in ("H", "f"):
                    row = max(0, min(height - 1, (numbers[0] if numbers else 1) - 1))
                    col = max(0, min(width - 1, (numbers[1] if len(numbers) > 1 else 1) - 1))
                elif command_name == "G":
                    col = max(0, min(width - 1, (numbers[0] if numbers else 1) - 1))
                elif command_name == "d":
                    row = max(0, min(height - 1, (numbers[0] if numbers else 1) - 1))
                elif command_name in ("A", "B", "C", "D"):
                    amount = numbers[0] if numbers and numbers[0] else 1
                    row += -amount if command_name == "A" else amount if command_name == "B" else 0
                    col += amount if command_name == "C" else -amount if command_name == "D" else 0
                    row, col = max(0, min(height - 1, row)), max(0, min(width - 1, col))
                elif command_name == "J" and numbers and numbers[0] == 2:
                    screen = [[" "] * width for _ in range(height)]
                elif command_name == "K":
                    mode = numbers[0] if numbers else 0
                    start, stop = (0, col + 1) if mode == 1 else (col, width) if mode == 0 else (0, width)
                    screen[row][start:stop] = [" "] * (stop - start)
                i = end + 1
                continue
            if i + 1 < len(text) and text[i + 1] == "]":
                end = text.find("\x07", i + 2)
                i = len(text) if end < 0 else end + 1
                continue
            i += 3 if i + 1 < len(text) and text[i + 1] == "(" else 2
            continue
        if char == "\r":
            col = 0
        elif char == "\n":
            row = min(height - 1, row + 1)
        elif char == "\b":
            col = max(0, col - 1)
        elif char == "\t":
            col = min(width - 1, (col + 8) // 8 * 8)
        elif char >= " " and char != "\x7f":
            if row < height and col < width:
                screen[row][col] = char
                cell_width = 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
                for offset in range(1, cell_width):
                    if col + offset < width:
                        screen[row][col + offset] = " "
                col = min(width - 1, col + cell_width)
        i += 1
    return "\n".join("".join(line).rstrip() for line in screen)


def interact(send):
    if "--interact" not in sys.argv:
        return
    def wait_for(marker):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if marker in screen_text():
                return
            time.sleep(0.025)
        raise RuntimeError(f"F3 smoke did not observe {marker!r}: {''.join(output)[-2000:]}")

    def expect_intermediate(start):
        time.sleep(0.08)
        if len("".join(output)) <= start:
            raise RuntimeError("F3 transition emitted no intermediate terminal frame")

    wait_for("F3 PLAYER")
    cursor = len("".join(output))
    send("\x1bOR")  # F3 enters Player Mode.
    expect_intermediate(cursor)
    wait_for("F3 EXIT")
    cursor = len("".join(output))
    send("\x1bOR")  # F3 returns to the library.
    expect_intermediate(cursor)
    wait_for("F3 PLAYER")


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
    print("F3 entered Player Mode and returned to the library" + (" with motion and intermediate frames." if motion_mode else "."))
