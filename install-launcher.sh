#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.local/share/icons/hicolor/scalable/apps"
python3 - "$project_dir" <<'PY'
from pathlib import Path
import shlex
import sys
root = Path(sys.argv[1])
home = Path.home()
wrapper = home/'.local/bin/ttools'
wrapper.write_text('#!/bin/sh\nexport PYTHONPATH='+shlex.quote(str(root))+'${PYTHONPATH:+:$PYTHONPATH}\nexec python3 -m ttools "$@"\n')
wrapper.chmod(0o755)
desktop = home/'.local/share/applications/ttools.desktop'
desktop.write_text('[Desktop Entry]\nType=Application\nName=ttools\nComment=Все терминальные инструменты в одном месте\nExec=konsole --separate --profile ttools -e "'+str(wrapper)+'"\nIcon=ttools\nTerminal=false\nCategories=Utility;\nStartupNotify=false\n')
konsole = home/'.local/share/konsole'
konsole.mkdir(parents=True, exist_ok=True)
for source in (root/'konsole').iterdir():
    (konsole/source.name).write_text(source.read_text())
icon = root/'icon.svg'
(home/'.local/share/icons/hicolor/scalable/apps/ttools.svg').write_text(icon.read_text())
print('Установлено. Запуск: ttools')
PY
