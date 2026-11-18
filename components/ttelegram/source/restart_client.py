"""Wait for the old worker to save and release its database before restarting."""
import os,sys,time
from pathlib import Path
old=int(sys.argv[1]) if len(sys.argv)>1 else 0
print('Сохраняю чат и черновики. Восстанавливаю Telegram…',flush=True)
for _ in range(100):
    status=Path(f'/proc/{old}/status')
    if not old or not status.exists():break
    try:
        line=next(x for x in status.read_text().splitlines() if x.startswith('State:'))
        if 'Z' in line:break
    except (OSError,StopIteration):break
    time.sleep(.1)
os.execv(sys.executable,[sys.executable,str(Path(__file__).parent/'client.py')])
