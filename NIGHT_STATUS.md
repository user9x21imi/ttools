# NIGHT_STATUS — TTools integration (integration/windows-preview)

Worktree: `C:\Users\user\source\repos\ttools-integration`
Owner: local integrator (Strata). Do not touch other agents' worktrees.

## Latest verified commits
- `9724404` integration base (Beam Free): launcher transparency + component discovery
- `1e24639` checkpoint: preserved prior agent TVPN work (panel redesign, splash, demo UI, updater guard, vendored docs)
- `1353cf6` merge `fix/tvpn-windows-runtime` (OpenVPN Interactive Service backend, Windows doctor)
- `c9f10af` TVPN fixes: reduced motion, region chooser helper, graph buckets, hardened Windows installer restored, VERSION/update.json = 1.4.1, bkgd removed, PTY tests skip on Windows
- `36da29c` merge `feature/ttelegram-modernization` (PR #7 draft)
- `a81e226` merge `origin/fix/tthings-windows-runtime` (Nemotron Ultra; conflicts were line-ending noise only)
- `dcb5fa6` pin windows-native payload as binary (`-text`) so SHA-256 manifests survive `core.autocrlf=true`; ignore downloaded bootstrap
- `5a5fd9c` refresh windows-native files.json/SHA256SUMS.txt after modernization merge
- `7820274` night status/tasks docs; pytest skips downloaded runtime payload
- `3e173b5` align suite/dev version catalogs with TVPN 1.4.1 (required by release validation)
- `08cc137`, `e397cb2` night report + TSoundCloud cross-platform test fix
- `72469c1` direct VT backend for launcher on Windows (`ttools/vtbackend.py`, PDCurses fallback for headless) — reviewed: no bkgd, default `-1` backgrounds emit no SGR, full curses API used by launcher/components present
- `8a0965d` TTelegram: find `wt.exe` via per-user app execution alias
- `364baf7`, `67416f4` night docs + VT shims for TSpotify/TVPN (`_vt.py`) and TTelegram launch hardening; `docs/WINDOWS_VT_TRANSPARENCY_DIAGNOSIS.md` committed
- `7e4ddde`, `4c320ad`, `b18fe95`, `eddca75` final night status/task updates; all commits pushed to `origin/integration/windows-preview`

## Component state
| Component | Branch/commits | State | Tests |
|-----------|----------------|-------|-------|
| Launcher (ttools) | merged `fix/update-feed-and-refresh` + fixes + `72469c1` | dev + installed catalog confirmed (4 apps in Windows install); direct VT backend on interactive Windows consoles | 79 passed, 12 skipped, 6 subtests |
| TSpotify | `fix/tspotify-windows-runtime` @ `590bc42` MERGED | verify-runtime OK in isolated Windows install | 397 passed, 2 skipped |
| TVPN | `fix/tvpn-windows` + `fix/tvpn-windows-runtime` + `c9f10af` | Windows backend pwsh, doctor, splash, demo UI, reduced motion, region helper, graph; offline only | 13 passed, 5 skipped (PTY POSIX-only) |
| TTelegram | `feature/ttelegram-modernization` MERGED + Windows payload downloaded | installer/doctor OK; wt.exe alias, bundle auto-install, trampoline argv fixed; real auth not attempted | 12 passed, 1 skipped |
| tthings | `origin/fix/tthings-windows-runtime` MERGED | VT console modes, UTF-8 subprocesses, gallery preview | 60 passed, 7 skipped, 4870 subtests |
| TSoundCloud | Linux preview only | NOT in standard Windows install | 14 passed, 3 skipped (cross-platform test fixture fixed) |

## Transparency contract
- Launcher, TSpotify, TVPN: no `bkgd()`; `use_default_colors()` + pairs with `-1` background.
- On Windows the launcher, TSpotify and TVPN now use a direct VT backend (`ttools/vtbackend.py` + per-component `_vt.py` shims, `72469c1`/`67416f4`) when a real console is attached; PDCurses remains the headless fallback. The VT backend preserves `-1` backgrounds (no explicit background SGR) in contrast to PDCurses, which normalizes `-1` to a concrete palette entry. `tests/test_vtbackend.py` guards this (6 passed).
- `docs/WINDOWS_VT_TRANSPARENCY_DIAGNOSIS.md` documents the PDCurses root cause and the backend migration; it is committed.
- Windows visual verification in Windows Terminal with transparency/Acrylic/image remains manual. Automated absence of forced ANSI background sequences is not proof of visual transparency.

## Build/test package (verified)
- Command: `python tools/build_release.py --output C:\Users\user\AppData\Local\Temp\opencode\ttools-test-release --platform windows-x86_64`
- Artifact: `ttools-windows-x86_64.zip` — 159,104,127 bytes; bundle checksums verified by `verify_bundle`.
- Isolated install: `python installer.py --prefix C:\Users\user\AppData\Local\Temp\opencode\ttools-test-prefix --bundle . --no-shortcuts --defer-system`
- Result: `{"installed": "1.1.0-preview.4", "complete": false, "unsupported": []}` — no PATH/registry changes, no VPN privileged setup, no system network changes.
- Installed launcher list: tspotify, ttelegram, tvpn, tthings (empty "00" catalog regression fixed in installed mode via suite runner setting TTOOLS_CATALOG).
- Smoke: tthings `--version` 0.7.2; tspotify `verify-runtime` JSON OK; tvpn `version`/`status`/`doctor` OK (OpenVPN present/not connected, Interactive Service running); ttelegram Windows-native `doctor` OK (tdlib 1.8.66).
- Final rebuild after all fixes: `python tools/build_release.py --output C:\Users\user\AppData\Local\Temp\opencode\ttools-final-release --platform windows-x86_64` → 159,117,158 bytes; isolated install to `C:\Users\user\AppData\Local\Temp\opencode\ttools-final-prefix --no-shortcuts --defer-system` → `{"installed":"1.1.0-preview.4","complete":false,"unsupported":[]}`; `runner.py --list` shows 4 supported apps. No user install or system changes.

## Remote state
- Pushed `integration/windows-preview` `9724404..eddca75` to `origin`; local branch matches remote, no pending commits.
- Created Draft PR #8: `https://github.com/user9x21imi/ttools/pull/8` (base `main`).
- A cloud VT agent had switched this worktree to `fix/vt-console-mode-transparency`; the branch was safely restored to `integration/windows-preview` and all of that agent's work was preserved, reviewed and integrated. No in-flight edits remain.

## Blockers (need user)
- Real VPN connect (OpenVPN) — offline/demo checks only at night.
- Real Telegram authorization + playback; TSpotify real login/audio.
- Visual transparency acceptance in Windows Terminal.

## Reproduce commands
```
cd C:\Users\user\source\repos\ttools-integration
python -m pytest tests -q
python -m pytest components/tvpn/source/tests -q
python -m pytest components/tspotify/source/tests -q
python -m pytest components/ttelegram -q
python -m pytest components/tthings/source/tests -q
python -m ttools --list
```
