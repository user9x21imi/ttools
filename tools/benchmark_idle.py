"""Linux-only live PTY CPU sample; synthetic catalog, no accounts or GUI."""
import os,pty,fcntl,termios,struct,tempfile,subprocess,time,select,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
results=[]
for flags in ([],['--low-power'],['--no-motion']):
 with tempfile.TemporaryDirectory(prefix='ttools-idle-') as temp:
  folder=Path(temp);catalog=folder/'apps.json';catalog.write_text(json.dumps({'apps':[{'id':app,'name':app,'command':['/usr/bin/true'],'suite_managed':True,'update_owner':'ttools','version':'demo'} for app in ('tspotify','ttelegram','tvpn','tthings')]}))
  master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',40,120,0,0))
  env=dict(os.environ,TERM='xterm-256color',XDG_CONFIG_HOME=temp,TTOOLS_CATALOG=str(catalog));process=subprocess.Popen([sys.executable,'-m','ttools','--no-splash','--background','light_bloom',*flags],stdin=slave,stdout=slave,stderr=slave,env=env,cwd=ROOT,start_new_session=True);os.close(slave)
  def pump(seconds):
   end=time.monotonic()+seconds
   while time.monotonic()<end:
    if select.select([master],[],[],.04)[0]:
     try:os.read(master,65536)
     except OSError:break
  def cpu():
   data=Path(f'/proc/{process.pid}/stat').read_text().split();return (int(data[13])+int(data[14]))/os.sysconf('SC_CLK_TCK')
  try:
   pump(1);start_cpu=cpu();start=time.monotonic();pump(3);wall=time.monotonic()-start
   results.append({'mode':flags or ['default'],'one_core_cpu_percent':round((cpu()-start_cpu)/wall*100,1),'wall_seconds':round(wall,2),'terminal':[120,40]})
   os.write(master,b'q');pump(.3);process.wait(timeout=3)
  finally:
   if process.poll() is None:process.kill();process.wait()
   os.close(master)
(ROOT/'docs/idle-cpu.json').write_text(json.dumps({'method':'Linux /proc process CPU after 1s warmup, 3s samples, real PTY loop, four synthetic catalog entries; one sample per mode, background secondary random','results':results},indent=2)+'\n')
print(json.dumps(results),flush=True)
