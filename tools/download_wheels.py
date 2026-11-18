"""CI: collect Telegram's pinned, unmodified Linux/CPython 3.14 dependencies."""
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
wheels=root/'components/ttelegram/wheels';wheels.mkdir(parents=True,exist_ok=True)
subprocess.run([sys.executable,'-m','pip','download','--only-binary=:all:','--dest',str(wheels),
               '-r',str(root/'components/ttelegram/source/requirements.txt')],check=True)
