# NIGHT_STATUS — TTools integration (integration/windows-preview)

Worktree: `C:\Users\user\source\repos\ttools-integration`
Owner: local integrator (Strata). Do not touch other agents' worktrees.

## Latest verified commits
- `9724404` integration base (Beam Free): launcher transparency + component discovery
- `1e24639` checkpoint: preserved prior agent TVPN work (panel redesign, splash, demo UI, updater guard, vendored docs)
- `1353cf6` merge `fix/tvpn-windows-runtime` (OpenVPN Interactive Service backend, Windows doctor)
- `c9f10af` TVPN fixes: reduced motion, region chooser helper, graph buckets, hardened Windows installer restored, VERSION/update.json = 1.4.1, bkgd removed (transparency), PTY tests skip on Windows

## Component state
| Component | Branch/commits | State | Tests |
|-----------|----------------|-------|-------|
| Launcher (ttools) | merged `fix/update-feed-and-refresh` + `c53e299` | catalog auto-discovery, no bkgd | tests/test_backgrounds.py, tests/test_windows_regression.py — run |
| TSpotify | `fix/tspotify-windows-runtime` @ `590bc42` MERGED | msvcrt lock, intro fix, no bkgd | 397 passed, 2 skipped |
| TVPN | `fix/tvpn-windows` + `fix/tvpn-windows-runtime` merged + `c9f10af` | Windows backend pwsh, doctor, splash, demo UI, reduced motion restored | 13 passed, 5 skipped (PTY POSIX-only) |
| TTelegram | `feature/ttelegram-modernization` @ `d7767a8` NOT merged | pending integration | win-native tests |
| tthings | `fix/tthings-windows-runtime` — Nemotron Ultra active | DO NOT EDIT; integrate after agent finishes | check HANDOFF.md + new commits |
| TSoundCloud | Linux preview only | NOT in standard Windows install | Windows: 1 path-separator failure |

## Transparency contract
- Launcher, TSpotify, TVPN: no `bkgd()`; `use_default_colors()` + pairs with `-1` background.
- Windows verification: manual check required in Windows Terminal (transparency/Acrylic/image). Automated absence of ANSI background sequences is not proof of visual transparency.

## Blockers (need user)
- Real VPN connect (OpenVPN) — offline/demo checks only at night.
- TTelegram real authorization + playback.
- TSpotify real login/real audio playback.
- Visual transparency acceptance in Windows Terminal.

## Test build path
- Not built yet. Stage D next: `tools/build_release.py`, install to separate test prefix only.

## Reproduce commands
```
cd C:\Users\user\source\repos\ttools-integration
python -m pytest components/tvpn/source/tests -q
python -m pytest components/tspotify/source/tests -q
python -m pytest tests -q
python -m ttools --list
```
