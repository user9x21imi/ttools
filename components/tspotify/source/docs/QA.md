# Offline QA setup

The project metadata in `pyproject.toml` is the canonical dependency list. Use an
isolated Python 3.11+ environment so the UI tests do not depend on packages installed
for another project.

## Linux and macOS

```sh
python3 -m venv .venv-qa
.venv-qa/bin/python -m pip install -e '.[dev]'
.venv-qa/bin/python -m pytest -q
TERM=xterm-256color .venv-qa/bin/python scripts/smoke_terminal.py --source --interact --ctrl-q --compact
```

## Windows PowerShell

```powershell
py -3.11 -m venv .venv-qa
.\.venv-qa\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv-qa\Scripts\python.exe -m pytest -q
$env:TERM = 'xterm-256color'
.\.venv-qa\Scripts\python.exe scripts/smoke_terminal.py --source --interact --ctrl-q --compact
```

The smoke runs the Python source with `--demo`, which supplies synthetic tracks and
cover art and replaces audio capture with a no-device stub. It checks the visible
`F3 PLAYER` → `F3 EXIT` → `F3 PLAYER` cycle. It does not log in, make Spotify requests,
or access audio hardware. On Windows, `pywinpty` is installed through the declared
platform dependency so the same scenario runs in a pseudo-terminal.

To smoke-test a built native executable instead, replace `--source` with its path.
