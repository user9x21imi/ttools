#!/usr/bin/env python3
"""Click-to-install entry for an already downloaded and extracted platform ZIP."""
import argparse
from pathlib import Path
import subprocess
import sys
from bootstrap import prepare_linux,python314
from ttools.distribution import prefix_path,platform_id,verify_bundle
from ttools.suite import APP_IDS,plan

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--allow-partial',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    metadata=verify_bundle(root)
    if metadata['platform']!=platform_id():raise RuntimeError('Download the ZIP for this OS/architecture')
    proposal=plan(root,platform_id(),APP_IDS,args.allow_partial)
    prefix=prefix_path()
    prepare_linux(proposal['install'])
    python=python314(prefix)
    argv=[str(python),str(root/'installer.py'),'--prefix',str(prefix)]
    if args.allow_partial:argv.append('--allow-partial')
    subprocess.run(argv,check=True)
    if '-' in metadata['version']:(prefix/'channel').write_text('preview',encoding='utf-8')
    print('Installed. Open a new terminal and run: ttools')
    if proposal['unsupported']:print('Not included on this OS: '+', '.join(proposal['unsupported']))
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as error:
        print('ttools: '+str(error),file=sys.stderr);raise SystemExit(1)
