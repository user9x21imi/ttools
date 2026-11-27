# TTools Integration Handoff

**Branch:** `integration/windows-preview`
**Worktree:** `C:\Users\user\source\repos\ttools-integration`
**Base Commit:** `1827e6b` (fix(windows): real Windows support for TSpotify, tthings, TVPN, installer + regression tests)

## Completed Work

### 1. Main Launcher Fixes
- **Fixed "Приложения / 00" issue**: Added `_dev_catalog_path()` in `ttools/core.py` to auto-discover `apps.local.json` from source tree when no user sources configured
- **Fixed terminal transparency**: Removed `self.s.bkgd(' ', curses.color_pair(1))` call in `ttools/__main__.py:colors()` which drew opaque gray background over terminal transparency/acrylic
- **Added safe default colors**: Wrapped `curses.use_default_colors()` in try/except to handle platforms where it's not supported (Windows PDCurses)

### 2. Component Discovery
- Created `apps.local.json` with 5 components pointing to local source directories:
  - `tspotify` (0.2.0-dev) - Music and your library
  - `tthings` (0.7.2-dev) - Effects and system tools
  - `tsoundcloud` (0.1.0-dev) - SoundCloud and track comments (Linux preview)
  - `tvpn` (1.3.1-dev) - Secure connection
  - `ttelegram` (2026.11.18.7-win1-dev) - Messages and channels (Windows-native)
- All components show "готово" (ready) in launcher

### 3. Terminal Transparency Contract
All components now follow the transparency contract:
- **Launcher** (`ttools/__main__.py`): Removed `bkgd()`, added `use_default_colors()` try/except
- **TSpotify** (`components/tspotify/source/src/tspotify/ui.py`): Nemotron removed `bkgd()` calls in App and _IntroRenderer
- **TVPN** (`components/tvpn/source/riseup-panel.py`): Removed `screen.bkgd(' ', curses.color_pair(5))`
- **TThings**: No `bkgd()` calls found (already compliant)
- **TTelegram**: No `bkgd()` calls found (Windows-native uses vtcurses stub)
- **TSoundCloud**: No `bkgd()` calls found (already compliant)

### 4. Integrated Component Updates
Merged from upstream branches:
- **TSpotify** (`fix/tspotify-windows-runtime`): Windows runtime lock (msvcrt), PR #6 artist discovery, transparency fix, 397 tests pass
- **TTelegram** (`feature/ttelegram-windows-runtime-ui`): Chat transitions (4 phases), VT initialization, Windows packaging tests
- **TVPN** (`feature/tvpn-terminal-redesign`): Globe animation, offline panel, terminal capture tests, rollback contract docs

### 5. Test Results
| Component | Platform | Tests | Status |
|-----------|----------|-------|--------|
| TSpotify | Windows | 397 passed, 2 skipped | ✅ |
| TThings | Windows | 60 passed, 7 skipped | ✅ |
| TTelegram (win-native) | Windows | 6 passed, 1 skipped, 3 failed (missing binary artifacts) | ⚠️ |
| TVPN (Windows tests) | Windows | 13 passed | ✅ |
| TTools regression | Windows | 13 passed | ✅ |
| TSoundCloud | Windows | 13 passed, 3 skipped, 1 failed (path separator) | ⚠️ |

Notes:
- TTelegram failures: Missing `bootstrap/` and `wheels/` directories (not checked in, downloaded at build time)
- TSoundCloud failure: Path separator issue in test (Windows `\\` vs Linux `/` in JSON), not functional

## Pending / Next Steps

### 1. TVPN Windows Agent
Local Strata/Qwen agent is working on TVPN Windows fixes. Do not merge until their work is complete and tested.

### 2. SoundCloud on Windows
Currently Linux-only preview. Do not present as working Windows component. Keep in dev catalog for testing only.

### 3. Cross-Platform Verification
- Test on Linux (primary platform for TTelegram, TSoundCloud)
- Test on macOS (TSpotify, TThings source-compatible)
- Verify terminal transparency works on all platforms (Windows Terminal, Konsole, iTerm2, etc.)

### 4. Update System Validation
- Verify suite update flow: component fix → integration branch → GitHub Actions build → manifest → user auto-update
- Test rollback with TVPN protected backend
- Validate checksum verification and atomic state transitions

### 5. Release Preparation
- Do NOT merge to main until:
  - TVPN Windows agent completes
  - All components pass cross-platform tests
  - Full suite update cycle validated
  - User acceptance testing on clean Windows install

## Configuration

### Environment Variables
- `TTOOLS_CATALOG`: Optional override for apps catalog path
- `TTOOLS_PREFIX`: Optional override for installation prefix
- `TTOOLS_CHANNEL`: Set to "preview" for preview updates
- `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`: Set by launcher on Windows

### Key Files
- `apps.local.json`: Development component catalog (auto-discovered)
- `ttools/core.py`: `_dev_catalog_path()` for source tree detection
- `ttools/__main__.py`: Launcher UI with transparency support
- `components/*/app.json`: Component metadata (version, launch args, etc.)

## Known Issues
1. **TTelegram Windows-native**: Requires Windows Terminal 1.22+ with SIXEL support. Bootstrap Python and wheels not in repo.
2. **TSoundCloud**: Browser login uses Zen/Chrome profile; Windows path handling in tests needs fix.
3. **TVPN Windows**: System setup (WireGuard, routing) requires elevated privileges; deferred mode available.
4. **Terminal transparency**: Requires terminal that supports default background (Windows Terminal, Konsole, etc.). PDCurses on legacy conhost may not support.

## Commands
```bash
# Run launcher with dev catalog
cd C:\Users\user\source\repos\ttools-integration
python -m ttools --list

# Run component tests
cd components/tspotify/source && python -m pytest tests/
cd components/tthings/source && python -m pytest tests/
cd components/tvpn/source && python -m pytest tests/test_offline_panel.py tests/test_update_lifecycle.py tests/test_windows_installer.py
cd components/ttelegram/windows-native && python -m pytest tests/test_core.py::Core::test_four_stage_transition_uses_all_states -v

# Run TTools regression tests
python -m pytest tests/test_windows_regression.py -v
```