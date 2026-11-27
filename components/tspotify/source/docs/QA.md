# Offline QA setup

The project metadata in `pyproject.toml` is the canonical dependency list. Use an
isolated Python 3.11+ environment so the UI tests do not depend on packages installed
for another project.

## Linux and macOS

```sh
python3 -m venv .venv-qa
.venv-qa/bin/python -m pip install -e '.[dev]'
.venv-qa/bin/python -m pytest -q
TERM=xterm-256color .venv-qa/bin/python scripts/smoke_terminal.py --source --interact --ctrl-q --compact --motion
```

## Windows PowerShell

```powershell
py -3.11 -m venv .venv-qa
.\.venv-qa\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv-qa\Scripts\python.exe -m pytest -q
$env:TERM = 'xterm-256color'
.\.venv-qa\Scripts\python.exe scripts/smoke_terminal.py --source --interact --ctrl-q --compact --motion
```

The smoke runs the Python source with `--demo`, which supplies synthetic tracks and
cover art and replaces audio capture with a no-device stub. `--motion` keeps the
panel transition enabled, verifies that intermediate terminal frames were emitted,
and checks the visible `F3 PLAYER` → `F3 EXIT` → `F3 PLAYER` cycle. It does not log in,
make Spotify requests, or access audio hardware. On Windows, `pywinpty` is installed
through the declared platform dependency so the same scenario runs in a pseudo-terminal.

For a still frame suitable for debugging, run the smoke at `--compact` (80×24) or omit
it (140×48). The deterministic tests also render transition progress at fixed timestamps,
so they cover both entry and exit between completed frames.

## Captures and component manifest

The offline capture script `python scripts/capture_qa.py` writes:

- [Library, 120×40](qa-artifacts/library-120x40.png)
- [F3 Player Mode, 120×40](qa-artifacts/player-120x40.png)
- [Artist profile, 120×40](qa-artifacts/artist-profile-120x40.png)
- [F3 entrance and exit](qa-artifacts/f3-transition.gif)
- [Offline render timings](qa-artifacts/performance.txt)

The package and component manifests currently agree on `0.2.0` (`pyproject.toml`,
`src/tspotify/__init__.py`, `components/tspotify/app.json`, `components/tspotify/update.json`,
and `components/versions.json`). The source checksum inventory is refreshed for this preview.
No release artifact is published by this QA run.

Linux source QA: 382 tests passed, one skipped, and four loopback-dependent tests were
deselected because this sandbox cannot bind local TCP sockets. The motion-enabled PTY
smoke passed at 80×24 and 140×48; fixed-time transition tests cover 80×24, 120×40, and
180×50. Native Windows/macOS terminal QA for this new preview remains pending.

To smoke-test a built native executable instead, replace `--source` with its path.
