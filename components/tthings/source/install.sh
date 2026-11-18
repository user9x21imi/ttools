#!/bin/sh
set -eu
cd -- "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ -x ./tthings-bin ]; then
    exec ./tthings-bin --install
elif command -v python3 >/dev/null 2>&1; then
    exec python3 -m tthings --install
else
    echo 'Нужна готовая сборка tthings для вашей системы; исходный архив требует Python 3.10+.' >&2
    exit 1
fi
