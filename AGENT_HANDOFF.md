# Windows support / launcher integration handoff

**Branch:** `fix/windows-support-and-launch`
**Worktree:** `C:\Users\user\source\repos\ttools-windows-support`
**Base:** `origin/pr/3` (`7cc0385`); commits `1827e6b` + `e4ebbef` (not pushed, no PR created).

## Scope owned here
TSpotify, tthings, the launcher and the Windows installer. **TVPN source files were
reverted to base** — the TVPN Windows agent owns them. TTelegram is owned by another
agent. Do not merge the full `integration/windows-preview` branch into this one until
the TVPN agent signs off, even though that branch is based on `1827e6b`.

## What is fixed
- **TSpotify**: cross-platform `runtime_lock` (msvcrt on Windows, fcntl on POSIX),
  `verify-runtime`/`doctor`/`--demo`/`install-engine` work on Windows; pinned
  `spotify_player.exe` v0.25.2 with SHA-256.
- **tthings**: UTF-8 subprocess pipes and child probes, Windows VT console modes and
  key mapping, safe terminal restore, Windows Python fallback.
- **Launcher**: `_dev_catalog_path()` discovers the bundled dev catalog so a source
  checkout lists its components instead of `Приложения / 00`; explicit sources and
  `TTOOLS_CATALOG` still win. `curses.use_default_colors()` is guarded for PDCurses
  and `bkgd()` was removed so terminal transparency/acrylic survives.
- **Installer**: default component list excludes the Linux-only SoundCloud on
  Windows; user PATH is updated via `winreg` + `WM_SETTINGCHANGE`; UTF-8 shims;
  Windows-safe re-exec after an in-place update; `install.ps1` works in pwsh and
  PowerShell 5.1.

## Verification (Windows 11 x64)
- `python -m unittest discover -s tests` → **83 OK, 12 skipped**.
- `python -m unittest tests.test_windows_regression` → **15 OK**.
- `python -m pytest components/tspotify/source` → **372 passed, 2 skipped**
  (set `PYTHONPATH` to this worktree's `components/tspotify/source/src`; another
  worktree has an editable install that otherwise shadows `tspotify` and causes
  5 unrelated failures).
- `python -m pytest components/tthings/source` → **60 passed, 7 skipped** (+4870 subtests).
- `pwsh -File tests/windows/test_install_ps1.ps1` and PowerShell 5.1 → both pass.
- Real ConPTY flow: launcher lists `APPLICATIONS / 05`, launches tthings and TSpotify
  `--demo`, both children and launcher quit with **exit 0** and terminal restored.
- Real bundle: `build_release.py --output dist --platform windows-x86_64` →
  `install-local.py --allow-partial --defer-system` installs 4 components, prints
  `unsupported: ["tsoundcloud"]`, exit 0.

## Limitations / not verified
- Real Spotify OAuth login, playback and audio capture need a manual account check.
- Real VPN connection and admin elevation need manual confirmation (TVPN untouched).
- TTelegram Windows-native binary payload is downloaded at build time and was not
  exercised here.
- `apps.local.json` stores absolute paths for this checkout; it is a dev-only
  catalog, not part of an installed bundle.
- `gh` CLI is unavailable in this environment, so no draft PR was opened.

## Install / run on Windows 11 x64
```powershell
irm https://raw.githubusercontent.com/user9x21imi/ttools/main/install.ps1 | iex
# or from an extracted bundle:
python .\ttools\install-local.py --allow-partial --defer-system
# open a NEW terminal (PATH is refreshed), then:
ttools
```
