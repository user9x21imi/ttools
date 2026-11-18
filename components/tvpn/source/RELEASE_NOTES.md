TVPN 1.4.0 — ttools integration

- Add user installation without launching the panel or connecting VPN: install.py --prefix PATH --no-launch.
- Add explicit --defer-system for safe isolated tests (not a working VPN system setup).
- Add JSON management commands: version, check-update, status, doctor, stop, update.
- Keep TVPN updater as the single update owner; share a lifecycle kernel lock between UI, installer and updater.
- Refuse updates while active, if cleanup is pending/failed, or if the protected backend lock is busy/unreadable.
- Stop waits up to the requested timeout, never forcibly kills the process and never reconnects.
- Roll back user files if protected helper setup fails; protect root helper installation with system locks and rollback.
- Extend update manifest with app/platform/install metadata for ttools; retain legacy updater fields.

Initial privileged Linux setup still requires sudo; development tests use isolated user prefixes and never install system rules.
Native VPN connections on macOS/Windows remain unverified on physical devices; ttools management targets Linux x86_64 first.
