#!/bin/sh
set -eu
command -v python3 >/dev/null 2>&1 || { echo 'Python 3.10+ is required to bootstrap ttools. Install Python, then rerun.' >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo 'curl is required.' >&2; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ required"'
# Downloads are temporary; the actual release and every component are hash-checked.
ttools_work=$(mktemp -d)
trap 'rm -rf -- "$ttools_work"' EXIT HUP INT TERM
curl -fsSL --proto '=https' --proto-redir '=https' --connect-timeout 15 --max-time 90 https://raw.githubusercontent.com/user9x21imi/ttools/main/bootstrap.py -o "$ttools_work/bootstrap.py"
python3 "$ttools_work/bootstrap.py" "$@"
