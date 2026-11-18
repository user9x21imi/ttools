"""Small POSIX engine guardian: a closed frontend must never leave music playing."""

import os
import signal
import subprocess
import sys
import time


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    parent = int(args[0])
    if os.getppid() != parent:
        return 1

    def stop(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGHUP, stop)
    process = subprocess.Popen(args[1:])
    try:
        while process.poll() is None:
            if os.getppid() != parent:
                return 1
            time.sleep(0.2)
        return process.returncode
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
