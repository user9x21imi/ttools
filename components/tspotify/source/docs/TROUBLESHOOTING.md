# Troubleshooting

**A command fails or stays pending.** Errors are shown in the status panel. Spotify may rate-limit
shared application IDs or reject a request. Respect the displayed wait. Check `tspotify devices`,
or use `--device integrated` to avoid selecting an unintended phone/speaker.

**The engine cannot load audio.** Spotify's audio server may be unreachable even while the Web API works.
Check your network and Premium account; use an already-running official Spotify Connect device if available.
Do not confuse an accepted Web API request with confirmed decoded playback.

**No music after muted testing.** `--muted` starts at zero. Raise volume deliberately with `+`.
The Linux stream mute left by a zero-volume test is cleared only by an explicit positive-volume action.

**Dots are missing / squares appear.** Use a Unicode monospace font or `tspotify --ascii`.
No private-use icon font is needed. Windows Terminal is recommended over legacy conhost.

**No spectrum.** Linux captures only the integrated Spotify stream with `parec --monitor-stream`; no stream means no bars. On Windows/macOS, route Spotify alone into a dedicated virtual channel and set `TSPOTIFY_SPOTIFY_LOOPBACK` to its exact input name/ID. The old `TSPOTIFY_LOOPBACK` shared-output option is ignored. External Connect playback has no local audio stream. Playback remains independent; hide the spectrum with `L`, then `v`.

**QR callback fails on a phone.** The callback is a loopback address on the computer. Copy the complete
callback address from the phone and paste it in the QR sign-in prompt. Do not send it to anyone.

**Wrong redirect address.** Re-run `tspotify login`. The Web API uses `/ncspot_login`; the separate streaming
identity uses `/login`. A client ID must match the registered callback.

**You closed tspotify but hear music.** The current version stops its integrated engine on every exit.
A separately running desktop Spotify or another Connect device is independent; stop it in that app.
An older prototype process can be identified with your OS process viewer. `tspotify doctor` shows paths,
not credentials.

**Unsigned downloaded binary.** macOS/Windows may request OS approval. The installer never disables
Gatekeeper, SmartScreen, certificate validation or system protections.


**F7–F12 do nothing when minimized.** A terminal does not receive unfocused input. On KDE, run `tspotify install-shortcuts` once and restart. The client reports an ownership conflict if another desktop action uses the key. On other desktops, assign `tspotify control volume-up/down` commands using their shortcut settings. The foreground client must be running; these controls do not autostart it.
