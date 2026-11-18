"""Native Windows entry: bundled Python + VT frontend + native TDLib."""
import argparse,json,os,sys,threading,time,uuid
from pathlib import Path

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--fast',action='store_true');parser.add_argument('--version',action='store_true');parser.add_argument('--demo',action='store_true');parser.add_argument('--prefix',type=Path);args=parser.parse_args()
    root=Path(__file__).resolve().parent
    if args.version:print((root/'VERSION').read_text().strip());return 0
    from process_control import default_prefix,data_root,lock
    prefix=Path(args.prefix or os.environ.get('TTELEGRAM_PREFIX') or default_prefix()).resolve();data=data_root();data.mkdir(parents=True,exist_ok=True)
    try:data_lock=lock(data/'account-instance.lock');instance_lock=lock(prefix/'run/instance.lock')
    except OSError:
        if 'data_lock' in locals():data_lock.close()
        print('Telegram уже открыт. Закройте предыдущее окно через Ctrl+Q.');return 2
    token=uuid.uuid4().hex;pidfile=prefix/'run/process.json';flag=prefix/'run/stop.request';flag.unlink(missing_ok=True)
    pidfile.write_text(json.dumps({'pid':os.getpid(),'token':token,'root':str(root),'version':(root/'VERSION').read_text().strip()}),encoding='utf-8')
    os.environ['TTELEGRAM_PREFIX']=str(prefix);os.environ['TTELEGRAM_STOP_FILE']=str(flag);os.environ['TTELEGRAM_RUN_TOKEN']=token
    done=threading.Event();tdlib_ref=[]
    try:
        import windows_bootstrap
        windows_bootstrap.install()
        import vtcurses
        vtcurses.prepare_console_output()
        import client
        original=client.QrTdlib.__init__
        def remember(self,*a,**kw):original(self,*a,**kw);tdlib_ref.append(self)
        client.QrTdlib.__init__=remember
        def watch_login():
            while not done.wait(.1):
                if flag.is_file() and flag.read_text(encoding='utf-8').strip()==token:
                    import recovery
                    if recovery.CURRENT is None:
                        if tdlib_ref:
                            try:tdlib_ref[-1].stop(close_timeout=3)
                            except Exception:return
                        os._exit(0)
        threading.Thread(target=watch_login,daemon=True,name='login-stop-request').start()
        if not args.fast:
            from ui import splash
            splash()
        if args.demo:
            from demo_backend import run_demo
            run_demo();return 0
        while True:
            try:client.run_client();return 0
            except client.LoginRetry:
                print('Соединение авторизации закрыто. Enter — повторить, q — выйти.')
                if input().strip().lower()=='q':return 0
                # Runtime patches are installed once per process. Retry cleanly.
                os.execv(sys.executable,[sys.executable,str(__file__),'--fast','--prefix',str(prefix)])
    finally:
        done.set()
        try:
            if json.loads(pidfile.read_text())['token']==token:pidfile.unlink(missing_ok=True)
        except (OSError,ValueError,KeyError):pass
        flag.unlink(missing_ok=True);instance_lock.close();data_lock.close()
if __name__=='__main__':
    try:raise SystemExit(main())
    except KeyboardInterrupt:raise SystemExit(0)
