"""Microphone-only recording draft shown inside the composer, never in a modal."""
import collections,math,struct,subprocess,threading,time
from voice_recorder import VoiceView

def microphone():
    default=subprocess.run(['pactl','get-default-source'],capture_output=True,text=True,timeout=3).stdout.strip()
    if default and not default.endswith('.monitor'):return default
    result=subprocess.run(['pactl','list','short','sources'],capture_output=True,text=True,timeout=3)
    for line in result.stdout.splitlines():
        fields=line.split()
        if len(fields)>1 and not fields[1].endswith('.monitor'):return fields[1]
    raise ValueError('Микрофон не найден. Выберите источник записи в настройках звука.')

class InlineVoice(VoiceView):
    def __init__(self,controller,source=None):
        super().__init__(controller,source=source or ['-f','pulse','-i',microphone()])
        self.levels=collections.deque([0.0]*80,maxlen=80);self.reader=None
    @classmethod
    def restore(cls,controller,item):
        voice=cls(controller,source=['-f','pulse','-i','default']);voice.path.unlink(missing_ok=True)
        from pathlib import Path
        voice.path=Path(item['path']);voice.duration=item['duration'];voice.waveform=item['waveform'];voice.state='review';voice.keep=True
        return voice
    def start(self):
        self.error='';self.errors.seek(0);self.errors.truncate()
        self.proc=subprocess.Popen(['ffmpeg','-y','-hide_banner','-loglevel','error',*self.source,
            '-map','0:a:0','-ac','1','-c:a','libopus','-b:a','32k',str(self.path),
            '-map','0:a:0','-ac','1','-ar','8000','-f','s16le','pipe:1'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.errors)
        self.started=time.monotonic();self.state='recording'
        def read():
            while True:
                block=self.proc.stdout.read(800)
                if not block:break
                values=struct.unpack('<'+'h'*(len(block)//2),block[:len(block)//2*2])
                rms=math.sqrt(sum(value*value for value in values)/max(1,len(values)))/32768
                self.levels.append(min(1.0,rms*5))
        self.reader=threading.Thread(target=read,daemon=True,name='microphone-waveform');self.reader.start()
    def stop(self):
        if self.state!='recording':return
        if self.proc.poll() is None:
            try:self.proc.stdin.write(b'q\n');self.proc.stdin.flush();self.proc.wait(timeout=3)
            except (BrokenPipeError,OSError,subprocess.TimeoutExpired):self.proc.kill();self.proc.wait()
        if self.reader:self.reader.join(timeout=1)
        if self.proc.returncode or self.path.stat().st_size<100:
            self.state='error';self.error='Не удалось записать микрофон. Ctrl+G — повторить.';return
        from features import voice_metadata
        self.duration,self.waveform=voice_metadata(str(self.path));self.state='review'
    @property
    def playing(self):return self.player is not None and self.player.poll() is None
    def bars(self,width):
        values=list(self.levels)[-max(1,width):]
        if self.state=='recording' and time.monotonic()-self.started>.5 and self.proc.poll() is not None:self.stop()
        return ''.join('▁▂▃▄▅▆▇█'[min(7,int(value*8))] for value in values)
    def draft(self):
        if self.state!='review':return None
        self.keep=True
        return {'kind':'voice','path':str(self.path),'owned':True,'duration':self.duration,'waveform':self.waveform}
