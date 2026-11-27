#!/usr/bin/env python3
"""Machine entry point for ttools. Never starts a VPN or a terminal UI."""
import argparse
import dataclasses
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import updater

ROOT=Path(__file__).resolve().parent


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=ROOT)
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('version','check-update','status','doctor'):sub.add_parser(name)
    apply=sub.add_parser('update');apply.add_argument('--manifest',type=Path)
    stop=sub.add_parser('stop');stop.add_argument('--timeout',type=float,default=30)
    args=parser.parse_args(argv);root=args.root.resolve()
    try:
        if args.command=='version':result={'version':updater.local_version(root)}
        elif args.command=='check-update':
            found=updater.check(root)
            result={'version':updater.local_version(root),'available':dataclasses.asdict(found) if found else None}
        elif args.command=='status':result=updater.lifecycle_status(root)
        elif args.command=='doctor':
            import platform,shutil
            windows=sys.platform=='win32'
            if windows:
                commands=('curl','pwsh','powershell','openvpn','openvpn-gui','winget','icacls','sudo')
                prog=Path(os.environ.get('ProgramFiles',r'C:\Program Files'))/'OpenVPN/bin'
                gui=prog/'openvpn-gui.exe';openvpn=prog/'openvpn.exe'
                service=_windows_service_state('OpenVPNServiceInteractive')
                in_group=_windows_admin_group_member()
            else:
                commands=('bash','python3','curl','ip','flock','sudo','visudo','openvpn')
                gui=None;openvpn=None;service=None;in_group=None
            result={'platform':sys.platform,'architecture':platform.machine(),'version':updater.local_version(root),
                    'commands':{x:shutil.which(x) for x in commands},
                    'openvpn_gui':str(gui) if gui else None,'openvpn_gui_present':bool(gui and gui.is_file()),
                    'openvpn_present':bool(openvpn and openvpn.is_file()) or bool(shutil.which('openvpn')),
                    'openvpn_interactive_service':service,'openvpn_administrator':in_group,
                    'protected_backend':Path('/var/lib/riseup-vpn/backend.sh').is_file(),
                    'network_tested':False,'system_rules_modified':False,'admin_required_for_connection':windows}
        elif args.command=='update':
            if args.manifest:
                found=updater.parse_manifest(json.loads(args.manifest.read_text(encoding='utf-8')),updater.local_version(root))
            else:found=updater.check(root)
            if found:updater.apply(found,root)
            result={'version':updater.local_version(root),'updated':bool(found),'launched':False}
        else:
            if not 0<args.timeout<=300:raise updater.UpdateError('timeout must be between 0 and 300 seconds')
            status=updater.lifecycle_status(root)
            if status['running']:
                # Only the process holding the lifecycle lock, never an arbitrary saved PID.
                pid=status.get('pid')
                if not pid:raise updater.UpdateError('Running process has no verified PID; stop it in its terminal')
                os.kill(pid,signal.SIGTERM)
                deadline=time.monotonic()+args.timeout
                while updater.lifecycle_status(root)['running']:
                    if time.monotonic()>=deadline:raise updater.UpdateError('Cleanup timeout; process not killed, update forbidden')
                    time.sleep(.1)
            updater.require_clean(root)
            with updater.backend_idle():pass
            result={'stopped':True,'cleanup':'ok' if (root/'.cleanup.json').exists() else 'no_session','reconnected':False}

        print(json.dumps({'app_id':'tvpn','ok':True,**result},ensure_ascii=False));return 0
    except (updater.UpdateError,OSError,ValueError) as error:
        print(json.dumps({'app_id':'tvpn','ok':False,'error':str(error)},ensure_ascii=False));return 1


def _windows_service_state(name):
    try:
        import shutil as _shutil
        ps=_shutil.which('pwsh.exe') or _shutil.which('pwsh') or _shutil.which('powershell.exe') or 'powershell.exe'
        result=subprocess.run([ps,'-NoProfile','-NonInteractive','-Command',
            f"(Get-Service -Name '{name}' -ErrorAction SilentlyContinue).Status"],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
        return (result.stdout.strip() or None) if result.returncode==0 else None
    except (OSError,subprocess.SubprocessError):
        return None


def _windows_admin_group_member():
    try:
        import shutil as _shutil
        ps=_shutil.which('pwsh.exe') or _shutil.which('pwsh') or _shutil.which('powershell.exe') or 'powershell.exe'
        user='[Security.Principal.WindowsIdentity]::GetCurrent().Name'
        result=subprocess.run([ps,'-NoProfile','-NonInteractive','-Command',
            f"$m=Get-LocalGroupMember -Group 'OpenVPN Administrators' -ErrorAction SilentlyContinue; $u={user}; if($m.Name -contains $u){{'True'}}else{{'False'}}"],
            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
        return (result.stdout.strip().lower()=='true') if result.returncode==0 else None
    except (OSError,subprocess.SubprocessError):
        return None


if __name__=='__main__':sys.exit(main())
