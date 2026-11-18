"""Build a self-contained matching platform with its offline logo catalog."""
from pathlib import Path
import importlib.util
import os
import subprocess
import sys

root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root))
args=[sys.executable,'-m','PyInstaller','--noconfirm','--onefile','--name','tthings-bin','--paths',str(root),'--collect-data','tthings']
if importlib.util.find_spec('tzdata'):args+=['--collect-data','tzdata']
if sys.platform!='linux' and not importlib.util.find_spec('psutil'):
    raise SystemExit('Build dependency psutil is required for Windows/macOS monitoring; install it into the build environment.')
args+=['--add-data',str(root/'licenses')+os.pathsep+'licenses','--add-data',str(root/'THIRD_PARTY_NOTICES.md')+os.pathsep+'.',str(root/'run.py')]
raise SystemExit(subprocess.call(args,cwd=root))
