"""Linux-only launcher CPU samples in a live PTY; synthetic catalog, no GUI."""
import fcntl,json,os,pty,select,struct,subprocess,sys,tempfile,termios,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MODES=(('idle-paused',(),.8),('animated',(),None),('no-motion',('--no-motion',),None))
REPEATS=2;WARMUP=1.5;SAMPLE=3.
results=[]

def sample(mode,flags,pause_at):
 with tempfile.TemporaryDirectory(prefix='ttools-idle-') as temp:
  folder=Path(temp);catalog=folder/'apps.json'
  catalog.write_text(json.dumps({'apps':[{'id':app,'name':app,'command':['/usr/bin/true'],'suite_managed':True,'update_owner':'ttools','version':'demo'} for app in ('tspotify','tsoundcloud','ttelegram','tvpn','tthings')]}))
  master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',40,120,0,0))
  env=dict(os.environ,TERM='xterm-256color',XDG_CONFIG_HOME=temp,TTOOLS_CATALOG=str(catalog))
  process=subprocess.Popen([sys.executable,'-m','ttools','--no-splash','--background','light_bloom',*flags],stdin=slave,stdout=slave,stderr=slave,env=env,cwd=ROOT,start_new_session=True);os.close(slave)
  started=time.monotonic();paused=False
  def pump(seconds):
   nonlocal paused
   end=time.monotonic()+seconds
   while time.monotonic()<end and process.poll() is None:
    elapsed=time.monotonic()-started
    if pause_at is not None and not paused and elapsed>=pause_at:
     os.write(master,b' ');paused=True
    if select.select([master],[],[],.03)[0]:
     try:os.read(master,65536)
     except OSError:break
  def cpu():
   data=Path(f'/proc/{process.pid}/stat').read_text().split()
   return (int(data[13])+int(data[14]))/os.sysconf('SC_CLK_TCK')
  try:
   pump(WARMUP)
   start_cpu=cpu();start=time.monotonic();pump(SAMPLE);wall=time.monotonic()-start
   result={'mode':mode,'one_core_cpu_percent':round((cpu()-start_cpu)/wall*100,2),'wall_seconds':round(wall,2),'terminal':[120,40]}
   os.write(master,b'q');process.wait(timeout=3)
   return result
  finally:
   if process.poll() is None:process.kill();process.wait()
   os.close(master)

for name,flags,pause_at in MODES:
 samples=[sample(name,flags,pause_at) for _ in range(REPEATS)]
 results.append({'mode':name,'one_core_cpu_percent_samples':[item['one_core_cpu_percent'] for item in samples],
                 'mean_one_core_cpu_percent':round(sum(item['one_core_cpu_percent'] for item in samples)/len(samples),2),
                 'wall_seconds':SAMPLE,'terminal':[120,40]})
(ROOT/'docs/idle-cpu.json').write_text(json.dumps({'method':f'Linux /proc process CPU, {WARMUP}s warmup, {SAMPLE}s measurement, {REPEATS} runs per mode, live 120x40 PTY, five synthetic apps; idle-paused receives Space before sample, animated leaves tthings motion active, no-motion uses the flag','results':results},indent=2)+'\n')
print(json.dumps(results),flush=True)
