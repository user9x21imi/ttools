#!/bin/sh
set -eu
cd -- "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# This platform preview intentionally contains no native Telegram package.
exec python3 install-local.py --allow-partial
