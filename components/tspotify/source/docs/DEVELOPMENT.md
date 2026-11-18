# Architecture and validation

The UI is Python/curses. Windows uses windows-curses; the streaming engine receives a ConPTY
through pywinpty. Unix uses a pseudo-terminal. Neither tmux nor ffmpeg is a runtime dependency.

Modules:

- `auth.py`: OAuth authorization code flow with PKCE and state validation; private token refresh.
- `api.py`: one pooled HTTP/2 client, rate-limit handling, paginated caches and verified controls.
- `backend.py`: pinned binary download/integrity checks, process ownership, local transport and player events.
- `art.py`: Pillow resizing and bounded artwork caches; public oEmbed thumbnail discovery.
- `audio.py`: Spotify-only stream capture and vectorized NumPy FFT. It never falls back to the mixed system output or automatically selects a physical microphone.
- `ui.py`: rendering, keyboard focus, panel order and targeted animation updates.
- `cli.py`: one active UI, first-run setup, diagnostics and unconditional engine cleanup.

`pytest` covers callback/CSRF handling, token lifetime, current and historical Spotify JSON shapes,
playlist pagination, stale favorite state, rejected commands, confirmed playback, archive extraction,
platform selection, artwork, FFT/silence, all keyboard categories, thumbnails, small windows and resizing.

CI builds and smoke-tests native binaries on four OS/architecture combinations. It does **not**
have a Spotify account or audio hardware. A successful build is not a claim of physical-device playback testing.

Local live tests must use `--muted` and, on Linux, mute the Spotify output stream as a second guard.
Never add account tokens to CI, screenshots, fixtures, git, or release artifacts.

To build locally:

```sh
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check src tests scripts
python -m PyInstaller --onedir --console --name tspotify --paths src --collect-all qrcode --collect-all PIL scripts/frozen_entry.py
python scripts/package_release.py linux-x86_64
```

For a release, download artifacts from the successful CI run for the exact commit being tagged.
Combine their `.sha256` files into `SHA256SUMS.txt`, attach all platform zips, the Python wheel/source
archive, install scripts and checksums, and publish the versioned GitHub release.


To check Linux spectrum isolation without audible output:

```sh
python scripts/check_spectrum_isolation.py
```

The check creates its own null sink, sends two different tones to two separate streams, and confirms that the per-stream monitor contains only the selected tone. It never changes the default sink or connects the test sink to hardware, and removes its owned streams/module afterwards. Run only where PulseAudio/PipeWire and `pactl`, `parec`, `paplay` are available.

Desktop control uses an authenticated localhost endpoint in `control.py`, with private, ephemeral `DATA/control.json` metadata. Never include that token/file in bundles. KDE registration in `shortcuts.py` is opt-in, checks existing ownership and releases its F7–F12 bindings on normal client exit. Commands enter the UI event queue and share the same coalesced volume worker as mouse and keyboard input. Test with a mock receiver to avoid changing audible playback.
