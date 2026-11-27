# TVPN — Windows runtime handoff (fix/tvpn-windows-runtime)

Component: `components/tvpn`
Branch: `fix/tvpn-windows-runtime` (worktree: `C:/Users/user/source/repos/ttools-fix-tvpn-windows-runtime`)

## Verified state at handoff (2026-11-27)

- Real VPN connection on Windows verified end-to-end:
  - Backend: `Backend('amsterdam').run()` via `openvpn-gui --command connect` (OpenVPN Interactive Service).
  - Connected IP: `212.129.37.129` (NL). Interface: `OpenVPN Data Channel Offload`.
  - Geo verified via ipwho.is (Amsterdam NL).
  - Route `0.0.0.0/1` installed and cleaned up on disconnect.
- OpenVPN installed: 2.7.9 (I002) amd64; service `OpenVPNServiceInteractive` Running/Automatic; user in `OpenVPN Administrators`.
- All runnable offline tests pass: 13 tests OK (offline panel, update lifecycle, windows installer). `tests/test_terminal_ui.py` cannot run on Windows (imports `fcntl`) — platform limitation, not a failure.

## Runtime fixes delivered in this branch

- `components/tvpn/source/platforms/windows/backend.py`
  - Added `powershell_exe()` preferring PowerShell 7+ (`pwsh.exe`, `pwsh`) then in-box Windows PowerShell 5.1.
  - `powershell(code, probe=False)`: raises on stderr; raises on empty-output non-probe failures; probe returns `''`.
- `components/tvpn/source/manage.py`
  - Windows `doctor`: checks commands, OpenVPN GUI, OpenVPN binary, Interactive Service state, admin group, `admin_required_for_connection`.

## Requirements for OpenVPN 2.7.9 on Windows (exact)

- Install OpenVPN Community 2.7.9 (I002) amd64 MSI.
- Install features: `ADDLOCAL=OpenVPN.GUI,OpenVPN.Service` (feature names: `OpenVPN.GUI`, `OpenVPN.Service`; `OpenVPN-GUI` is wrong).
- Install with elevation (error 1925 without admin).
- `ADDLOCAL=ALL` to provision the `ovpn-dco-win` driver (OpenVPN 2.7 default driver; `windows-driver wintun` deprecated, wintun removed).
- Interactive Service `OpenVPNServiceInteractive` must be Running / Automatic.
- User must be member of local group `OpenVPN Administrators` (create + add via `net localgroup` as admin).
- First network setup requires admin rights.

## Design

- Based on `origin/feature/tvpn-terminal-redesign` (terminal redesign: globe animation, demo mode, region UI, terminal captures).

## Constraints

- Do not add VPN configs with secrets, user data, temp files, venv, lifecycle.lock, cleanup.json.
- Do not edit the general launcher/installer/other programs.
- Do not merge or publish a release.

## Handoff

- Branch: `fix/tvpn-windows-runtime`
- Worktree: `C:/Users/user/source/repos/ttools-fix-tvpn-windows-runtime`
- Draft PR: pending push.
