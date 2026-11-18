"""Installation-relative commands; no shell concatenation of unquoted paths."""
import hashlib,os,shlex,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DEFAULT=Path.home()/'.local/share/ttelegram'
SOCKET=os.environ.get('TTELEGRAM_SOCKET') or ('ttelegram' if ROOT==DEFAULT else 'ttelegram-'+hashlib.sha256(str(ROOT).encode()).hexdigest()[:12])
def command(*argv):return shlex.join(map(str,argv))
def tmux_config():
    path=Path.home()/'.cache/ttelegram'/('tmux-'+SOCKET+'.conf');path.parent.mkdir(parents=True,exist_ok=True)
    text=(ROOT/'tmux.conf').read_text()
    text+='\nbind -n C-q run-shell '+shlex.quote(command(sys.executable,ROOT/'session_control.py'))+'\n'
    path.write_text(text);return path
