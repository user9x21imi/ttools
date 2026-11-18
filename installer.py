#!/usr/bin/env python3
"""Portable suite installer entry; importing it never starts an application."""
from ttools.suite import main
if __name__=='__main__':
    raise SystemExit(main())
