# tspotify 0.2.0 → ttools

Source is synchronized with `user9x21imi/tspotify` commit `5c64c3323acf493093c874f971f60a07284c472e` for version 0.2.0. The standalone release workflow builds Linux x86_64, macOS Apple Silicon/Intel, and Windows x64 archives. T Tools installs this component from `source/` in its managed Python environment; no native runtime archive is embedded in this component bundle.

## Startup screen

The Fastfetch-style system screen appears before the integrated engine starts. Engine startup runs in a worker while the screen animates, then the screen remains visible for three seconds after readiness. Startup errors are shown before the launcher returns to the terminal. `--no-splash` skips the screen and uses the synchronous startup path; QR engine authorization also keeps the terminal prompt visible.

The spectrum panel is included in the regular layout at 78×24, the common compact Terminal.app window size. At this size it uses one row of bars; taller windows provide more detail and library space.

## Platform behavior

- **Linux:** captures only the integrated Spotify PulseAudio/PipeWire stream with `parec --monitor-stream`.
- **macOS / Windows:** playback works from the bundled or pinned engine. Spectrum capture requires a dedicated Spotify audio input and `TSPOTIFY_SPOTIFY_LOOPBACK` set to its exact name or ID. Mixed system output and physical microphones are never selected automatically.
- **External Spotify Connect:** remote audio is not available locally, so no local spectrum is shown.

Standalone CI builds and runs offline smoke checks for all four OS/architecture targets. It does not validate account login, real playback, or audio capture on physical hardware for every OS. macOS and Windows spectrum behavior remains unverified on this machine.

## T Tools install and lifecycle

T Tools installs `source/` with its managed Python environment. Updates are owned by the T Tools suite and preserve Spotify tokens, preferences, cached artwork, and saved session data. The runtime paths are `${HOME}/.config/tspotify`, `${HOME}/.local/share/tspotify`, and `${HOME}/.cache/tspotify`; the legacy `${HOME}/.cache/spotify-player` cache is also preserved.

For an update, T Tools stops only its own running client and waits for the UI and integrated engine to exit before switching releases. A stop timeout rejects the update. No account tokens, OAuth callbacks, listening data, or cache files are included in the source bundle.
