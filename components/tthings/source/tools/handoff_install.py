#!/usr/bin/env python3
"""Standalone entry point for a ttools handoff bundle. No UI or hotkey changes."""
import argparse
import json
from pathlib import Path
import sys

bundle=Path(__file__).resolve().parent
source=bundle/'source'
if not (source/'tthings').is_dir():source=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(source))
from tthings.deployment import apply_update,rollback,stop_managed,read_metadata

def main():
    parser=argparse.ArgumentParser(description='tthings deployment for ttools')
    parser.add_argument('action',choices=['install','apply','rollback','stop','status'])
    parser.add_argument('--prefix',required=True)
    parser.add_argument('--manifest',default=str(bundle/'update.json'))
    parser.add_argument('--source-fallback',action='store_true',help='Explicitly choose the Python source zipapp')
    args=parser.parse_args()
    try:
        if args.action in ('install','apply'):result=apply_update(args.manifest,args.prefix,forced_platform='python-source' if args.source_fallback else None)
        elif args.action=='rollback':result=rollback(args.prefix)
        elif args.action=='stop':result=stop_managed(args.prefix)
        else:result=read_metadata(args.prefix)
        print(json.dumps(result,ensure_ascii=False));return 0
    except (OSError,RuntimeError,ValueError) as exc:
        print(json.dumps({'status':'error','app_id':'tthings','error':str(exc)},ensure_ascii=False),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
