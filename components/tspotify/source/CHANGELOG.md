# Changelog

## 0.2.0

- Show a refreshed Fastfetch-style system screen while the Spotify engine starts, then keep it visible for three seconds after the client is ready.
- Keep the spectrum panel visible in compact 78×24 terminals, including the default Terminal.app window on macOS.
- Start the engine alongside the intro, keep download and authorization output from corrupting the screen, and stop cleanly if startup is interrupted.
- Build and publish native archives for Linux x86_64, macOS Apple Silicon/Intel, and Windows x64 from the same tagged release.

## 0.1.0

- Keep shuffle/repeat buttons visible at stable positions across resizes and compact panels.
- Confirm the final applied mode instead of clearing repeat intent on intermediate native events.
- Restart saved end-of-track positions at zero and restore the actual queue for Next/Previous after startup.

- Use consistent timeline colors in full redraws and animated frames, eliminating the flashing full-width green bar.
- Adapt the main window to side-by-side playback/library panels in wide terminals.

- Restart an ended queue from zero with Play; Next can restart the queue after it has stopped, matching the native remote Resume behavior.
- Preserve uncached album/playlist contexts instead of replacing them with a one-track queue.
- Expose native upcoming tracks for an accurate Next label, including shuffled order and repeat-one.
- Adapt the expanded player to portrait and landscape terminals, keeping artwork on the left in wide windows.

- Closing Share/Jam dialogs preserves the expanded player and underlying layout; background animation cannot draw over modal dialogs.

- Native engine v5 applies shuffle and all repeat modes through local Connect controls and exposes authoritative player state.
- Fix truncated 100-track queue commands and upstream empty-selector handling for phone Connect selections.
- Add clickable Share and clipboard links for tracks/collections.
- Create/retrieve native Jam sessions asynchronously, display returned participants and a real invitation link.
- Keep shuffle/repeat buttons visible in compact and expanded playback views.

- Search inside an open playlist/album instantly by track, artist or album; F2 keeps global Spotify search available.
- Filtering keeps the original playback queue, and clearing the field/Esc restores all collection tracks.

- Focused search temporarily expands the result list above a compact player/spectrum, restoring the saved layout when returning to playback.
- Search results stay expanded while moving between the input and list; Esc, player focus and F3 restore the usual arrangement.

- Live search suggestions include cover thumbnails, artist, album and duration; stale replies cannot overwrite newer input.
- Select tracks through native Connect load when available, without Web API play/device-discovery round trips.
- Disable the embedded engine's competing custom queue; keep Spotify's native queue authoritative.
- Preload nearby artwork and metadata; update native playback state every 100 ms and immediately after commands.
- Background remote observation and missing metadata no longer block local playback updates.
- Preserve repeated transport inputs and allow replacing a pending track selection.

- Use Spotify access-point port 443 instead of hanging on blocked port 4070; network startup timeouts no longer incorrectly request another login.

- Keep the preferred volume separate from the engine's temporary boot mute; save volume at each user adjustment.
- Use the patched native engine's local IPC for volume, seek and transport; bypass Web API rate limits for integrated playback.
- Separate transport workers keep volume responsive while a track loads.
- Preserve a continuous progress clock and reject poll responses superseded by transport commands.

- Route hardware Media Play/Pause/Next/Previous and volume keys to the running KDE client, restoring system bindings on exit.
- Follow fresh phone/Connect selections without replaying the stored session or overwriting the external device target.
- Prevent stale local events from replacing newer Connect state; unknown durations no longer fill the progress bar.
- Display track durations in search and library lists.
- Bundle the streaming engine in native archives; add headless status/stop/runtime checks and managed ttools update ownership.

- Correct media mapping: F7 previous, F8 play/pause, F9 next, F10 mute, F11 quieter, F12 louder; migrates prior KDE bindings.
- Debounced, paced volume writes discard unchanged boundary values and retry the latest target automatically after Spotify Retry-After.

- Coalesced volume updates preserve rapid presses and reject stale poll levels; track startup cannot overwrite a newer user volume.
- Optional KDE F7–F12 desktop bindings and authenticated local control work without terminal focus and release keys on exit.
- Prioritized current-cover loading, appropriately sized CDN images and cached dotted rasters reduce artwork delays.

- Persistent volume, track/position and library view; explicit Space resumes the saved position without startup autoplay.
- Ctrl+Q exits from every input mode and saves the session; muted tests and demos preserve ordinary preferences.

- Single-click open/play, clickable volume and transport controls, footer actions and modal navigation.
- Spotify-only spectrum capture on Linux; shared system-output recording removed on all platforms.

- Numbered discovery sections: recent contexts/tracks, saved Spotify mixes, new releases, recommendations and saved daily mixes.
- Mouse panel focus, clickable tabs and controls, list selection/double-click and wheel scrolling.
- F3 expanded player with detailed 256×256 artwork and a smooth dotted audio spectrum.
- Re-activate registered Connect devices before retrying 404; recover stopped engines and failed controls, including automatic-device fallback.
- Stable release update checks with explicit confirmation and checksum verification.

- Colored dotted cover art, matching dotted splash, and small playlist/album covers.
- Framed terminal layout, inherited background/transparency and a plain-ASCII fallback.
- Search, playlists, albums, liked tracks, favorite toggling, volume/mute, shuffle and repeat.
- Enter opens a playlist; Enter on a track starts it in its original context.
- Playing is confirmed by a real engine event or remote Spotify state; errors are not success messages.
- Smooth real-audio FFT spectrum with separate attack/release interpolation.
- Persistent panel ordering and cover-side controls.
- Browser PKCE authorization and QR/manual-callback sign-in.
- Automatic selection of an available, already logged-in Spotify Connect device.
- Foreground-owned integrated engine, zero-volume test mode and shutdown on exit.
- Native release builds for Linux x64, macOS arm64/x64 and Windows x64.
- Per-user install scripts, checksum-verified engine downloads, CI tests and private credential storage.

