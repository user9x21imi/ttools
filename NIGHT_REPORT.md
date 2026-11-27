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
| repo root `python -m pytest tests -q` | 78 passed, 12 skipped, 6 subtests passed (incl. 5 VT-backend tests) |
| TVPN `components/tvpn/source/tests` | 13 passed, 5 skipped (POSIX PTY only) |
| TSpotify `components/tspotify/source/tests` | 397 passed, 2 skipped |
| TTelegram `components/ttelegram` | 9 passed, 1 skipped |
| tthings `components/tthings/source/tests` | 60 passed, 7 skipped, 4870 subtests |
| TSoundCloud `components/tsoundcloud/source/tests` | 14 passed, 3 skipped (test fixture now uses a real absolute path and parses JSON; TSoundCloud still not in standard Windows install) |

Installed-package smoke checks: launcher lists 4 supported apps; tthings `--version` = 0.7.2; TSpotify `verify-runtime` JSON ok; TVPN `version`/`status`/`doctor` ok (OpenVPN not connected); TTelegram Windows-native `doctor` ok. Update/rollback/checksum-protection E2E covered by root suites (`test_update_e2e_qa.py`, `test_complete_suite_update.py`, `test_release_gate.py`, `test_distribution.py`).

## Remote
- `git push origin integration/windows-preview`: `9724404..e397cb2`. Local `72469c1` (VT backend) and `8a0965d` (TTelegram wt.exe alias) plus in-flight cloud-agent fixes still await the final push.
- Draft PR #8 created: `https://github.com/user9x21imi/ttools/pull/8` (base `main`).
- Cloud VT agent's work was preserved: `72469c1` (direct VT backend for the launcher) is integrated and verified; `docs/WINDOWS_VT_TRANSPARENCY_DIAGNOSIS.md` is the agent's untracked analysis. The branch was restored to `integration/windows-preview` after the agent switched it; the agent is still editing TTelegram files here.

## Limitations — manual verification required
- Actual transparency/Acrylic/image inheritance in Windows Terminal (automated bkgd/ANSI checks are necessary but not sufficient).
- Real VPN connection, real Telegram authorization, real Spotify login/audio playback.
- Interactive resize / UTF-8 rendering in a live terminal: covered by mocked UI tests, not by a human visual pass.
- Other agent's processes (in a separate worktree) were left running; our own smoke processes exited cleanly.

## Worktree hygiene
- All verified commits are local on `integration/windows-preview`, ready to push.
- `ttools/vtbackend.py` and `tests/test_vtbackend.py` from the cloud VT agent are now committed (`72469c1`) and verified. Untracked `docs/WINDOWS_VT_TRANSPARENCY_DIAGNOSIS.md` and in-flight TTelegram modifications are preserved untouched until that agent finishes.
- No secrets, user DBs, Telegram sessions, VPN credentials, venvs or downloaded binary payloads are staged/committed (runtime/bootstrap/wheels are gitignored).
