"""Visible, mouse-friendly recording controls; never sends on the first Enter."""
from native_image import synchronized,begin_frame
import curses,os,subprocess,tempfile,time
from pathlib import Path
from tg.colors import get_color,cyan,bold

class VoiceView:
    def __init__(self,controller,source=None):
        self.controller=controller
        folder=Path.home()/'.cache/ttelegram/voice';folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd,name=tempfile.mkstemp(suffix='.ogg',prefix='voice-',dir=folder);os.close(fd)
        self.path=Path(name);self.source=source or ['-f','pulse','-i','default']
        self.proc=None;self.player=None;self.errors=tempfile.TemporaryFile();self.state='idle';self.error='';self.buttons=[]
        self.duration=0;self.waveform='';self.keep=False;self.last_frame=None
        self.recipient=next((c.get('title','Чат') for c in controller.model.chats.chats if c.get('id')==controller.model.current_chat_id),'Чат')
    def start(self):
        if self.player and self.player.poll() is None:self.player.terminate()
        self.error='';self.errors.seek(0);self.errors.truncate()
        self.proc=subprocess.Popen(['ffmpeg','-y','-hide_banner','-loglevel','error',*self.source,'-ac','1','-c:a','libopus','-b:a','32k',str(self.path)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=self.errors)
        self.started=time.monotonic();self.state='recording';self.last_frame=None
    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:self.proc.communicate(b'q\n',timeout=3)
            except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()
        if not self.proc or self.proc.returncode or self.path.stat().st_size<100:
            self.state='error';self.error='Не удалось записать микрофон. Проверьте выбранный источник звука.';return
        try:
            from features import voice_metadata
            self.duration,self.waveform=voice_metadata(str(self.path));self.state='review'
        except (OSError,ValueError,subprocess.SubprocessError):
            self.state='error';self.error='Запись пустая. Нажмите «Заново» и произнесите сообщение.'
        self.last_frame=None
    def play(self):
        if self.player and self.player.poll() is None:self.player.terminate();self.player=None
        else:self.player=subprocess.Popen(['ffplay','-nodisp','-autoexit','-loglevel','error',str(self.path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.last_frame=None
    def action(self,key):
        if key in ('cancel','chat_list','quit','settings'):return {'action':key}
        if key=='stop' and self.state=='recording':self.stop()
        elif key=='record' and self.state!='recording':self.start()
        elif key=='play' and self.state=='review':self.play()
        elif key=='send' and self.state=='review':
            self.keep=True
            return {'action':'send','path':str(self.path),'duration':self.duration,'waveform':self.waveform}
    @synchronized
    def draw(self,screen):
        if self.state=='recording' and self.proc.poll() is not None:self.stop()
        elapsed=int(time.monotonic()-self.started) if self.state=='recording' else self.duration
        playing=self.player is not None and self.player.poll() is None
        h,w=screen.getmaxyx();frame=(h,w,self.state,elapsed,playing,self.error)
        if frame==self.last_frame:return
        self.last_frame=frame;begin_frame(screen);screen.erase();self.buttons=[]
        accent=get_color(cyan,-1)|bold;red=get_color(curses.COLOR_RED,-1)|bold
        def put(y,x,text,attr=0):
            if 0<=y<h and x<w-1:
                try:screen.addstr(y,x,text[:max(0,w-x-1)],attr)
                except curses.error:pass
        put(0,2,'ГОЛОСОВОЕ СООБЩЕНИЕ',accent);put(2,2,'Кому: '+self.recipient)
        if self.state=='recording':
            put(5,4,f'● ИДЁТ ЗАПИСЬ   {elapsed//60:02}:{elapsed%60:02}',red)
            put(7,4,'Говорите в микрофон. Удерживать клавиши не нужно.')
            put(8,4,'Enter или Ctrl+G остановит запись. Это ещё не отправка.')
            controls=[('Остановить Enter','stop'),('Отменить Esc','cancel')]
        elif self.state=='review':
            put(5,4,f'ЗАПИСАНО {self.duration} СЕКУНД'+(' · ВОСПРОИЗВЕДЕНИЕ' if playing else ''),accent)
            put(7,4,'P — прослушать · Enter — отправить · R — заново · Esc — отменить')
            controls=[('Остановить прослушивание' if playing else 'Прослушать P','play'),('Отправить Enter','send'),('Заново R','record'),('Отменить Esc','cancel')]
        else:
            put(5,4,self.error or 'Запись остановлена.')
            controls=[('Заново R','record'),('Отмена Esc','cancel')]
        row=min(h-4,11);x=2
        for title,key in controls:
            text='['+title+'] '
            if x+len(text)>=w:row+=2;x=2
            put(row,x,text,accent);self.buttons.append((row,x,x+len(text)-1,key));x+=len(text)
        put(h-2,2,'Сообщение отправляется только кнопкой «Отправить» или Enter на экране готовой записи.')
        screen.refresh()
    def close(self):
        for proc in (self.player,self.proc):
            if proc and proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=1)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
        self.errors.close()
        if not self.keep:self.path.unlink(missing_ok=True)
    def run(self,screen):
        curses.curs_set(0);curses.mousemask(curses.ALL_MOUSE_EVENTS);screen.keypad(True);screen.timeout(100)
        try:
            self.start()
            while True:
                self.draw(screen)
                try:key=screen.get_wch()
                except curses.error:continue
                result=None
                if key in ('\n','\r',curses.KEY_ENTER):result=self.action('stop' if self.state=='recording' else 'send')
                elif key=='\x07':result=self.action('stop' if self.state=='recording' else 'record')
                elif key in ('\x1b','q'):result=self.action('cancel')
                elif key=='\x11':result=self.action('quit')
                elif key=='\x0c':result=self.action('chat_list')
                elif key=='\x0f':result=self.action('settings')
                elif key in ('p','P'):result=self.action('play')
                elif key in ('r','R'):result=self.action('record')
                elif key==curses.KEY_MOUSE:
                    try:_,x,y,_,buttons=curses.getmouse()
                    except curses.error:continue
                    if buttons&(curses.BUTTON1_PRESSED|curses.BUTTON1_CLICKED):
                        command=next((command for row,left,right,command in self.buttons if row==y and left<=x<right),None)
                        if command:result=self.action(command)
                if result:return result
        finally:self.close()

def show(controller):
    from overlay import open_overlay,run_modal
    with open_overlay(controller,'Голосовое · Enter — остановить / Esc — отменить'):
        return run_modal(controller,VoiceView(controller).run)
