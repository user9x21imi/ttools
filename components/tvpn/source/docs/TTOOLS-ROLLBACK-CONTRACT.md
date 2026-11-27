# TVPN contract for TTools suite rollback

**Status: blocked in the current shared suite updater.** `ttools/suite.py` refuses
to activate a previous suite release whenever `tvpn` is in the installed
component set. TVPN files and settings remain managed separately, so switching
the suite pointer alone would not restore a usable VPN backend.

## Required sequence

1. Hold the TTools suite update lock for the complete rollback transaction.
2. Ask the installed component's `manage.py stop --timeout N` to stop the UI and
   backend. Do not send a kill signal when the timeout expires.
3. Require a valid JSON response with `ok: true`, `stopped: true`, and cleanup
   equal to `ok` or `no_session`.
4. Require `manage.py status` to report `running: false`; check the protected
   backend lock is idle and readable. Any timeout, malformed response, cleanup
   failure, or busy/unreadable lock aborts rollback before changing the active
   suite pointer.
5. Preserve user settings and saved data. Activate the previous suite and
   verify that its TVPN install path, `VERSION`, launcher, and management API
   agree with the selected suite manifest.
6. If a later activation check fails, restore the pre-rollback suite pointer
   while leaving both release directories intact. Report failure; do not
   forcibly terminate the backend.

## Ownership

The suite must not download or unpack a TVPN component archive. TTools records
`update_owner: tvpn`; `manage.py update` owns TVPN's HTTPS/SHA256 validation,
shared lifecycle lock, protected-helper update, and rollback of files changed by
that component update. Suite rollback coordinates stop and version selection;
it does not duplicate the component updater.

## Checks needed before enabling

- Simulate successful and failed cleanup with `--defer-system`.
- Hold the UI lifecycle lock and confirm rollback refuses to proceed.
- Hold the protected backend lock and confirm rollback refuses to proceed.
- Force a candidate installer failure and prove the prior suite pointer remains
  active and both release directories remain available.
- Verify successful rollback preserves settings, does not reconnect, and makes
  the previous TVPN `version`, `status`, and `doctor` commands usable.
- Run the sequence on Linux, Windows, and macOS; current lifecycle and protected
  backend lock behavior differs by platform.

This contract is ready for the Launcher/Release maintainer. No corresponding
change is made to shared TTools code in the TVPN feature branch.
