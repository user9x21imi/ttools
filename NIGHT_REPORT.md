# NIGHT_REPORT — TTools Windows integration (integration/windows-preview)

Date: 2026-11-28 (night session). Worktree: `C:\Users\user\source\repos\ttools-integration`.

## Scope completed
1. TVPN regression repair: restored `reduced_motion` (globe), region chooser helper, graph bucket formula, hardened Windows installer, VERSION/update.json = 1.4.1, transparency (`bkgd()` removed), cross-platform PTY test skip, release version catalog alignment.
2. Integrated three pending component branches: TTelegram modernization, tthings Windows runtime (Nemotron Ultra), all other remote branches verified already merged.
3. Fixed Windows TTelegram payload verification: `core.autocrlf=true` was converting checked-in SHA-256-payload files to CRLF; `.gitattributes` marks the payload as binary and manifests were refreshed after the modernization merge. Downloaded payload via the verified tool (`tools/download_windows_telegram.py`, SHA-256 checked).
4. Fixed pytest collection collision between the downloaded runtime payload and repo tests (`norecursedirs`).
5. Built and installed a real Windows test package into an isolated prefix; no user install, no PATH/registry changes, no network/VPN setup changes.

## Exact commands
```
cd C:\Users\user\source\repos\ttools-integration
python tools/download_windows_telegram.py
python tools/build_release.py --output C:\Users\user\AppData\Local\Temp\opencode\ttools-test-release --platform windows-x86_64
Expand-Archive C:\Users\user\AppData\Local\Temp\opencode\ttools-test-release\ttools-windows-x86_64.zip -DestinationPath C:\Users\user\AppData\Local\Temp\opencode\ttools-test-bundle
cd C:\Users\user\AppData\Local\Temp\opencode\ttools-test-bundle\ttools
python installer.py --prefix C:\Users\user\AppData\Local\Temp\opencode\ttools-test-prefix --bundle . --no-shortcuts --defer-system
python C:\Users\user\AppData\Local\Temp\opencode\ttools-test-prefix\runner.py --list
```

## Test results (Windows 11, Python 3.14.10, PowerShell 7)
| Suite | Result |
|-------|--------|
| repo root `python -m pytest tests -q` | 79 passed, 12 skipped, 6 subtests passed (incl. 6 VT-backend tests) |
| TVPN `components/tvpn/source/tests` | 13 passed, 5 skipped (POSIX PTY only) |
| TSpotify `components/tspotify/source/tests` | 397 passed, 2 skipped |
| TTelegram `components/ttelegram` | 9 passed, 1 skipped |
| tthings `components/tthings/source/tests` | 60 passed, 7 skipped, 4870 subtests |
| TSoundCloud `components/tsoundcloud/source/tests` | 14 passed, 3 skipped (test fixture now uses a real absolute path and parses JSON; TSoundCloud still not in standard Windows install) |

Installed-package smoke checks: launcher lists 4 supported apps; tthings `--version` = 0.7.2; TSpotify `verify-runtime` JSON ok; TVPN `version`/`status`/`doctor` ok (OpenVPN not connected); TTelegram Windows-native `doctor` ok. Update/rollback/checksum-protection E2E covered by root suites (`test_update_e2e_qa.py`, `test_complete_suite_update.py`, `test_release_gate.py`, `test_distribution.py`).

## Final integration work (lead, 2026-11-28)
- Cherry-picked `8a0965d` (Windows Terminal app-alias discovery) and integrated the second cloud agent's TTelegram fixes: actionable error when `current.json` is missing, on-demand install for dev bundle prefixes, corrected `ttelegram.cmd` trampoline argv (`"%~dp0."`), plus regression tests. Payload `files.json` and `components/checksums.json` refreshed; all 12 TTelegram tests pass (1 skipped).
- Extended transparency fix beyond the launcher: new `_vt` shims in TSpotify (`src/tspotify/_vt.py`, selected in `cli.py`) and TVPN (`source/_vt.py`, selected in `riseup-panel.py`) load `ttools.vtbackend` on Windows when a console is available, otherwise fall back to stdlib curses. POSIX and headless test runs are unaffected.
- Final commit `67416f4 fix(windows): preserve terminal transparency in TSpotify/TVPN and harden TTelegram launch` (11 files) includes the diagnosis report `docs/WINDOWS_VT_TRANSPARENCY_DIAGNOSIS.md`.
- Final test results: root suite **79 passed, 12 skipped, 6 subtests**; TSpotify **397 passed, 2 skipped**; TVPN **13 passed, 5 skipped**; TTelegram **12 passed, 1 skipped**; tthings **60 passed, 7 skipped**; TSoundCloud **14 passed, 3 skipped**.

## Release build / one-command install (validated)
- Fresh release build from `72469c1`: `python tools/build_release.py --output C:\temp\ttg-night-release --platform windows-x86_64` → `ttools-windows-x86_64.zip` (94,158,950 bytes, `complete=False` because Windows Telegram payload is not yet published in a GitHub Release).
- Extracted ZIP to `C:\temp\ttg-night-unpacked\ttools`; ran `cmd /c "Install-ttools.cmd -Prefix C:\temp\ttg-one-cmd-test -Components tthings"` with `TTOOLS_INSTALLER_NO_PAUSE=1` → **exit 0**, installed tthings 0.7.2 into `1.1.0-preview.4`, no manual steps. One-command install validated end-to-end.
- Final rebuild after all fixes: `C:\temp\ttg-final-release\ttools-windows-x86_64.zip` (94,166,354 bytes). Full one-command install of all four apps with system setup deferred: `cmd /c "Install-ttools.cmd -Prefix C:\temp\ttg-final-test2 -DeferSystem"` → **exit 0**. `runner.py --list` shows all four apps ready; TSpotify `verify-runtime` ok; TVPN `version` 1.4.1 and `status` ok; TTelegram `doctor` ok. A run without `-DeferSystem` fails only because winget is absent in this environment (external dependency, not a code regression).

## Remote
- `git push origin integration/windows-preview`: `9724404..e397cb2`, then final `e397cb2..7e4ddde`. All commits are pushed; no local pending work. No GitHub Release was published — release awaits user acceptance.
- Draft PR #8 created: `https://github.com/user9x21imi/ttools/pull/8` (base `main`).
- All cloud-agent artifacts are now committed and verified; no in-flight TTelegram edits remain in this worktree.

## Limitations — manual verification required
- Actual transparency/Acrylic/image inheritance in Windows Terminal (automated bkgd/ANSI checks are necessary but not sufficient).
- Real VPN connection, real Telegram authorization, real Spotify login/audio playback.
- Interactive resize / UTF-8 rendering in a live terminal: covered by mocked UI tests, not by a human visual pass.
- Other agent's processes (in a separate worktree) were left running; our own smoke processes exited cleanly.

## Worktree hygiene
- All verified commits are local on `integration/windows-preview`, ready to push.
- `ttools/vtbackend.py`, `tests/test_vtbackend.py`, `docs/WINDOWS_VT_TRANSPARENCY_DIAGNOSIS.md` and all TTelegram launch fixes are committed and verified. Worktree is clean apart from this report update; no untracked diagnostics are staged.
- No secrets, user DBs, Telegram sessions, VPN credentials, venvs or downloaded binary payloads are staged/committed (runtime/bootstrap/wheels are gitignored).
