"""Native microphone/playback draft via PortAudio; Opus via bundled FFmpeg."""
import array,base64,collections,math,os,subprocess,tempfile,threading,time
from pathlib import Path

def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()
def run_media(arguments,**kwargs):
    if os.name=='nt':kwargs.setdefault('creationflags',subprocess.CREATE_NO_WINDOW)
    return subprocess.run(arguments,**kwargs)
class InlineVoice:
    def __init__(self,controller,source=None):
        self.controller=controller;folder=Path.home()/'.cache/ttelegram/voice';folder.mkdir(parents=True,exist_ok=True)
        fd,name=tempfile.mkstemp(suffix='.ogg',prefix='voice-',dir=folder);os.close(fd);self.path=Path(name)
        self.pcm_path=self.path.with_suffix('.pcm');self.state='idle';self.duration=0;self.waveform='';self.keep=False;self.error='';self.started=0
        self.levels=collections.deque([0.0]*80,maxlen=80);self.peaks=[];self.frames=0;self.rate=48000;self.input=None;self.output=None;self.file=None
        self._pcm=None;self._offset=0;self._playing=False;self.play_seconds=0.;self.play_duration=0.;self.lock=threading.Lock()
    def start(self):
        import sounddevice as sd
        self.file=self.pcm_path.open('wb');self.peaks=[];self.frames=0;self.error=''
        def capture(data,frames,timing,status):
            block=bytes(data);self.file.write(block);self.frames+=frames
            samples=array.array('h');samples.frombytes(block)
            rms=math.sqrt(sum(value*value for value in samples)/max(1,len(samples)))/32768
            self.levels.append(min(1,rms*5));self.peaks.append(max((abs(value) for value in samples),default=0))
        try:
            self.input=sd.RawInputStream(samplerate=self.rate,channels=1,dtype='int16',blocksize=2400,callback=capture)
            self.input.start();self.started=time.monotonic();self.state='recording'
        except Exception as problem:
            self.error='Микрофон недоступен: '+str(problem);self.state='error';self.file.close();self.file=None
    def stop(self):
        if self.state!='recording':return
        if self.input:self.input.stop();self.input.close();self.input=None
        if self.file:self.file.close();self.file=None
        if not self.frames:self.state='error';self.error='Запись пустая. Ctrl+G — повторить.';return
        result=run_media([ffmpeg(),'-v','error','-y','-f','s16le','-ar',str(self.rate),'-ac','1','-i',str(self.pcm_path),'-c:a','libopus','-b:a','32k',str(self.path)],capture_output=True,timeout=30)
        if result.returncode:self.state='error';self.error='Не удалось подготовить Opus-запись';return
        self.play_duration=self.frames/self.rate;self.duration=max(1,math.ceil(self.play_duration))
        count=len(self.peaks);values=[max(self.peaks[i*count//100:max(i*count//100+1,(i+1)*count//100)],default=0) for i in range(100)]
        peak=max(values) or 1;packed=sum(min(31,round(value*31/peak))<<(i*5) for i,value in enumerate(values))
        self.waveform=base64.b64encode(packed.to_bytes(63,'little')).decode();self.state='review';self.play_seconds=0.
    def play(self):
        import sounddevice as sd
        if self.playing:
            self._playing=False;self.output.abort();self.output.close();self.output=None;return
        if self.output:self.output.close();self.output=None
        if self._pcm is None:
            result=run_media([ffmpeg(),'-v','error','-i',str(self.path),'-f','s16le','-ac','1','-ar',str(self.rate),'pipe:1'],capture_output=True,timeout=30,check=True)
            self._pcm=result.stdout;self.play_duration=len(self._pcm)/(2*self.rate)
        self._offset=0;self.play_seconds=0.;self._playing=True
        def finished():
            if self._playing:self.play_seconds=self.play_duration
            self._playing=False
        def output(buffer,frames,timing,status):
            size=frames*2;data=self._pcm[self._offset:self._offset+size];buffer[:]=data+b'\0'*(size-len(data));self._offset+=len(data);self.play_seconds=self._offset/(2*self.rate)
            if len(data)<size:raise sd.CallbackStop
        try:
            self.output=sd.RawOutputStream(samplerate=self.rate,channels=1,dtype='int16',callback=output,finished_callback=finished)
            self.output.start()
        except Exception as problem:
            self._playing=False;self.error='Воспроизведение недоступно: '+str(problem)
            if self.output:self.output.close();self.output=None
    @property
    def playing(self):return self._playing
    @property
    def progress(self):return min(1,max(0,self.play_seconds/max(.01,self.play_duration or self.duration)))
    def bars(self,width):
        if self.state=='recording':values=list(self.levels)[-max(1,width):]
        else:
            packed=int.from_bytes(base64.b64decode(self.waveform or ''),'little');peaks=[((packed>>(i*5))&31)/31 for i in range(100)];size=max(1,min(100,width));values=[max(peaks[i*100//size:max(i*100//size+1,(i+1)*100//size)]) for i in range(size)]
        return ''.join('▁▂▃▄▅▆▇█'[min(7,int(value*8))] for value in values)
    def draft(self):
        if self.state!='review':return None
        self.keep=True
        return {'kind':'voice','path':str(self.path),'owned':True,'duration':self.duration,'waveform':self.waveform,'play_duration':self.play_duration}
    @classmethod
    def restore(cls,controller,item):
        voice=cls(controller);voice.path.unlink(missing_ok=True);voice.path=Path(item['path']);voice.pcm_path=voice.path.with_suffix('.pcm');voice.duration=item['duration'];voice.waveform=item['waveform'];voice.play_duration=item.get('play_duration',voice.duration);voice.state='review';voice.keep=True;return voice
    def close(self):
        self._playing=False
        if self.input:self.input.stop();self.input.close();self.input=None
        if self.output:self.output.abort();self.output.close();self.output=None
        if self.file:self.file.close();self.file=None
        self.pcm_path.unlink(missing_ok=True)
        if not self.keep:self.path.unlink(missing_ok=True)
