"""Run the bundled Python wheel directly without pip or a network request."""

import hashlib
from pathlib import Path
import runpy
import sys


def main():
    runtime = Path(__file__).resolve().parent / "runtime"
    name = "tsound-0.1.0-py3-none-any.whl"
    wheel = runtime / name
    expected, entry = (runtime / "SHA256SUMS").read_text(encoding="ascii").split()
    if entry != name or hashlib.sha256(wheel.read_bytes()).hexdigest() != expected:
        raise SystemExit("tsoundcloud: локальный пакет не прошёл проверку SHA-256")
    sys.path.insert(0, str(wheel))
    runpy.run_module("tsound", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
