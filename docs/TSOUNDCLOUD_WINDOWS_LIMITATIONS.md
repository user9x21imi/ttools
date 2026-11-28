# TSoundCloud on Windows — verified status and limitations

**Component:** `tsoundcloud` 0.1.0 (`tsound` wheel, verified by `launch.py` with SHA-256).
**Platform checked:** Windows 11, Python 3.14.6, `windows-curses` 2.4.2 (PDCurses).
**Status:** not a supported Windows component. It is intentionally excluded from the
Windows installer by `ttools/suite.py` (`UNSUPPORTED_BY_PLATFORM['windows-x86_64']`)
and the night build's `bundle.json` lists it under `unsupported_components`.

This document records what was actually verified during the night session and what
still prevents declaring Windows support. The acceptance criterion is
"Windows runtime works **or** documented limitations" — the latter is met here.

## Verified on Windows

| Check | Command | Result |
|-------|---------|--------|
| Verified wheel launch / version | `python components/tsoundcloud/launch.py --version` | `tsound 0.1.0`, exit 0; wheel SHA-256 check passes |
| Offline UI demo | `python components/tsoundcloud/launch.py --demo --no-splash` | Fixed a Windows-only crash (see below); now reaches the interactive UI loop. In a headless pipe it waits for input, as expected — it requires an interactive terminal. |
| Source test suite | `python -m pytest components/tsoundcloud/source/tests -q` | 17 passed, 3 skipped (PTY/audio tests are POSIX-only; 3 new Windows curses-compatibility tests) |

### Windows-only crash fixed

`tsound/ui.py::App.run()` called `curses.set_escdelay(35)` unconditionally.
`windows-curses` (PDCurses) does not provide that function, so the demo aborted with
`AttributeError: module 'curses' has no attribute 'set_escdelay'`. The call is now
guarded with `getattr` and wrapped in `curses.error`; the wheel and its `SHA256SUMS`
were rebuilt from the patched source. The short ESC delay remains on ncurses.

## Remaining limitations (why it is not shipped on Windows)

1. **Terminal transparency.** TSoundCloud uses PDCurses directly. On Windows,
   `init_pair(fg, -1)` is normalized to a concrete palette index and every cell is
   written with an explicit background, covering acrylic/background images in
   Windows Terminal. This is the same root cause documented in
   `docs/WINDOWS_VT_TRANSPARENCY_DIAGNOSIS.md`. No VT backend hook is applied because
   the component is not part of the Windows install; doing so would be the first
   step if Windows support is pursued.
2. **Audio.** Real playback needs FFmpeg, SDL2 and a working audio device. They are
   not bundled in the Windows handoff. `--demo` is deliberately silent; the audio
   tests are skipped on this platform.
3. **Browser login.** `tsound/web_session.py` locates a Zen Flatpak profile under
   `~/.var/app/...` and detects the default browser using Linux conventions. The
   Windows path layout, Edge/Chrome profile discovery and OAuth callback handling
   have not been implemented or tested.
4. **Lifecycle.** There is no external `stop` command; normal exit is Ctrl+Q
   (`0x11`) sent to the instance's own PTY. The ttools launcher cannot manage the
   app on Windows without adding that command.
5. **Updates.** No public update channel is configured for this component;
   `launch.py` only verifies the local wheel.

## Recommendation

Keep TSoundCloud as a Linux-only component. Users on Windows should use the Linux
package/WSL. If Windows support is requested later, the minimum work is:

- select `ttools.vtbackend` for the app (as done for TSpotify/TVPN),
- guard/verify all remaining curses API differences,
- add SDL2/FFmpeg dependency provisioning,
- implement Windows browser-profile discovery and an external stop command,
- then add it to `supported_components('windows-x86_64')` and release tests.
