#!/usr/bin/env python3
"""Synthetic, network-free event source for the actual TVPN curses panel."""
import argparse
import os
from pathlib import Path
import signal
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from riseup_regions import REGIONS

STOP=threading.Event()


def emit(*fields):
    print('@RISEUP\t'+'\t'.join(str(value) for value in fields),flush=True)


def request_stop(*_):
    STOP.set()


def read_commands():
    for line in sys.stdin:
        if line.strip().casefold()=='stop':
            STOP.set()
            return


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--text',action='store_true')
    parser.add_argument('--events',action='store_true')
    parser.add_argument('--region',choices=REGIONS,default='amsterdam')
    options=parser.parse_args(argv)
    signal.signal(signal.SIGINT,request_stop)
    if hasattr(signal,'SIGTERM'):signal.signal(signal.SIGTERM,request_stop)
    threading.Thread(target=read_commands,daemon=True).start()

    selected=options.region
    location=REGIONS[selected]
    emit('availability',selected,3,'synthetic')
    emit('location',selected,location['city'],location['country'])
    emit('state','catalog','Synthetic gateway catalog; no network request')
    time.sleep(.35)
    emit('state','certificate','Synthetic preparation; no certificate is read')
    time.sleep(.35)
    emit('state','connecting','Synthetic handshake; no tunnel is created')
    emit('gateway','demo-'+selected,location['city'])
    emit('interface','demo0')
    time.sleep(.35)
    emit('state','verifying','Synthetic result; no external IP check is performed')
    time.sleep(.35)
    emit('connected','198.51.100.23',location['country'])

    rx=tx=0
    tick=0
    emit('traffic',rx,tx)
    while not STOP.wait(.5):
        tick+=1
        # Repeatable counters make the graph move without inventing live data.
        rx+=(1+tick%5)*48*1024
        tx+=(1+(tick+2)%4)*32*1024
        emit('traffic',rx,tx)

    emit('state','disconnecting','Synthetic cleanup; no network state changed')
    failed=os.environ.get('TVPN_DEMO_CLEANUP_FAILURE')=='1'
    emit('cleanup','failed' if failed else 'ok')
    return 1 if failed else 0


if __name__=='__main__':
    raise SystemExit(main())
