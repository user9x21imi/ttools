# TVPN technical notes

## Source and version boundaries

This document describes `components/tvpn/source` on the TTools integration
branch. Its shipped metadata remains `VERSION` **1.3.1** and `update.json`
**1.3.1**. `RELEASE_NOTES.md` labels 1.4.0 as an unreleased integration
candidate. The standalone repository has advanced separately (its `main`
reported 1.4.1 when checked on 2026-11-23); this does not change TTools' source,
manifest, checksum, or release version.

## Terminal UI

`launch.py` chooses the platform backend and starts the same curses panel.
The panel polls input with a 100 ms timeout, so animation and key handling share
one loop. The globe is rendered from Natural Earth geometry, uses one persistent
camera, caches its eight most recent frames, and animates toward a newly selected
region. The layout stacks the globe, connection summary, and two traffic graphs
below 108 columns; at 108 columns and 30 rows it moves connection details to a
right-hand column. Curses restores the original terminal and color background.

`--no-motion` or `TVPN_NO_MOTION=1` snaps focus to the target and disables the
continuous-spin control. Arrows, zoom, region selection, logs, stop, reconnect,
and exit remain available.

`launch.py --demo` uses `demo_backend.py` through the actual curses event loop.
It does not acquire lifecycle locks, read a real interface, query the network,
or write cleanup markers. The reserved documentation IP `198.51.100.23`,
`demo-*` gateway, simulated verification, and counters are always labeled
synthetic; the simulated exit is never colored as a verified VPN exit.
For the explicit cleanup-failure PTY case, `TVPN_DEMO_CLEANUP_FAILURE=1`
makes the synthetic process report failure without changing network state.

## VPN and statistics

In a normal session, only a backend `connected` event with a valid external IP
and the selected region code moves the model to `connected`. The platform
backend performs tunnel and exit checks before emitting that event. The globe's
green selection indicates that reported event; the selected region by itself
uses the accent color. Statistics come from the selected tunnel interface.
Rates use byte-counter differences over the measured monotonic interval, and
the graph retains up to 60 samples. A new gateway resets the sample baseline.

Ctrl+S requests backend stop and keeps the panel open after cleanup. Ctrl+Q
closes the panel only after successful cleanup; on failure it leaves the error
visible. Ctrl+C stops in place. TERM and HUP use the backend's stop path. The UI
waits for it to exit and does not kill a backend on a cleanup timeout.
`manage.py stop` likewise
refuses to proceed after its timeout and verifies both the lifecycle and
protected backend locks before reporting cleanup.

## TTools update ownership

The TTools launcher records `update_owner: tvpn` for this component. Its
platform installer calls `install.py --prefix ... --no-launch` on Linux and
installs the component files before setting up the native helper on Windows or
macOS. `manage.py version`, `check-update`, `status`, `doctor`, `stop`, and
`update` are the component management interface. The TVPN updater owns TVPN
archives and uses its lifecycle lock; the suite updater must not unpack a TVPN
archive itself. `--defer-system` is only for isolated packaging tests and does
not create a usable VPN backend.

The current TTools suite explicitly refuses suite rollback when `tvpn` is in
the selected components (`ttools/suite.py::rollback`). This TVPN branch does
not change that shared release contract. A complete suite rollback must first
call `manage.py stop --timeout N`, require JSON `ok: true`, `stopped: true`, and
`cleanup: ok` (or `no_session`), then confirm `status.running == false` and that
the protected backend lock is idle. A timeout, malformed response, failed
cleanup, busy/unreadable lock, or missing management entry point must abort
rollback without killing the process or switching the active suite pointer.
Preserve user settings outside versioned files. After activating the previous
suite, verify its TVPN files and management API before marking rollback
successful. The exact maintainer handoff and test requirements are in
[`TTOOLS-ROLLBACK-CONTRACT.md`](TTOOLS-ROLLBACK-CONTRACT.md). This contract still
needs implementation and integration QA in the shared TTools updater.

## Reproducible checks

Run from `components/tvpn/source`:

```sh
python3 tests/test_offline_panel.py
python3 tests/test_terminal_ui.py
python3 tests/test_windows_installer.py
python3 tests/capture_terminal_ui.py
python3 tests/capture_terminal_visuals.py
python3 tests/capture_terminal_comparison.py
```

The PTY integration tests launch `launch.py --demo`; no privileged helper,
network request, tunnel, DNS change, or system configuration is used. The
capture utility writes asciinema v2 sessions from the PTY connected to that
same curses process. PNG and GIF exports replay the ANSI cells from those
recordings; they do not call a second UI renderer.

## Validation status

| Scenario | Status | Evidence / limit |
|---|---|---|
| Existing offline model tests | PASS | `tests/test_offline_panel.py` |
| Real curses startup and draw at 80×24, 120×40, 160×50 | PASS | PTY test with synthetic backend |
| Keyboard region menu, journal, stop, exit | PASS | PTY integration test |
| Resize from 80×24 to 120×40 while running | PASS | PTY integration test |
| Synthetic byte-rate calculation | PASS | Offline fixture; production interface counters are not changed |
| Linux install-only with `--defer-system` | PASS | Isolated temp prefix; no system rules changed |
| `manage.py version/status/doctor/stop` | PASS | Deferred install in temp prefix; stop returned `no_session` |
| `manage.py check-update` against the remote feed | NOT TESTED | The sandbox could not download the external update feed |
| Empty/unavailable selected region | PASS | Region chooser refuses a zero-gateway fixture; never silently changes region |
| Backend process failure / cleanup failure | PASS (synthetic guard) | PTY keeps the error visible when cleanup is unconfirmed; updater fixture blocks download |
| Busy component lifecycle lock | PASS | Update is rejected while UI owns the lock |
| Tunnel launch, real network loss, catalog outage, GeoIP outage, stats interface loss | NOT TESTED | Requires platform backend/network fixtures or a native host; no live VPN was started |
| Physical Linux VPN tunnel and cleanup | NOT TESTED | No authorized network test machine in this environment |
| Windows/macOS curses, installers, native tunnel, reconnect, cleanup | NOT TESTED | No Windows or macOS host available |
| Windows WinGet discovery contract | PASS (static) | `tests/test_windows_installer.py`; PowerShell runtime is not available here |
| UI CPU/RSS sample at 160×50 | PASS | 1.6% CPU idle, 11.2% with globe spin, 29 MiB RSS on this Linux host / CPython 3.14 |
| TTools suite rollback with TVPN | BLOCKED | Current shared code intentionally refuses rollback when TVPN is selected |
| 80×24 / 120×40 / 160×50 screen captures | PASS | PNGs exported from the corresponding real curses PTY recordings |
| Globe rotation / region transition / synthetic connection animation | PASS | GIFs exported from actual curses PTY recordings; synthetic connection is visibly labeled |

The synthetic session is not evidence of a real VPN connection. There is no
automatic kill switch on application crash.
