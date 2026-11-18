# Included components

| Component | Source | License / notices |
|---|---|---|
| tspotify | supplied clean handoff, commit b9de12e7124cdfc1b77753a09ab828e4e0885f26 | components/tspotify/source/LICENSE, NOTICE |
| TVPN | supplied local project 1.3.1 with install-only/lifecycle changes | components/tvpn/source/LICENSE, SOURCES.md, assets/licenses |
| tthings | supplied handoff 0.7.0 | components/tthings/source/LICENSE; Fastfetch notices shipped in source |
| ttelegram | supplied code allowlist 2026.11.18.4 | upstream tg Unlicense: components/ttelegram/source/vendor/TG-LICENSE.txt |
| tthings background renderers | earlier supplied handoff | ttools/visuals/LICENSE |

The ttools source adaptation to tspotify adds a Windows implementation of its
managed installation lock. The tthings InstanceLease adapter accepts
TTOOLS_TTHINGS_PREFIX so detached windows remain visible to the suite updater.
Its Windows CLI also selects UTF-8 for redirected Unicode/Braille output. Its license is preserved. The Telegram adapter contains
the author's tg/views.py patch and verifies the pinned original file before applying it.
Telegram runtime dependencies are distributed as unmodified wheels; each wheel
retains its own licenses. Spotify's optional streaming engine has separate notices
and checksum manifests supplied by the tspotify package.

No user venv, account configuration, credentials, message databases or logs are
included. The public Riseup CA certificate is application data, not a private key.
