"""Exercise the shared VT frontend on POSIX; not a Windows host certification."""
import os,sys,time,json,subprocess,tempfile,threading,struct,shutil
from pathlib import Path
if os.name=='nt':raise SystemExit('Use run.cmd --demo on Windows; this PTY harness is for POSIX')
import pty,fcntl,termios
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='Telegram UI тест ') as folder:
    folder=Path(folder);master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',45,140,1120,720))
    code="import os,runpy;from pathlib import Path;import windows_bootstrap;windows_bootstrap.install(native_td=False,configure_paths=False);runpy.run_path(str(Path(os.environ['TEST_SOURCE'])/'demo_scenario.py'),init_globals={'demo_path':lambda name:Path(os.environ['TTELEGRAM_DEMO_DIR'])/name})"
    env=dict(os.environ,PYTHONPATH=str(root/'source'),TEST_SOURCE=str(root/'source'),TTELEGRAM_DEMO_DIR=str(folder),TERM='xterm-256color')
    process=subprocess.Popen([sys.executable,'-c',code],env=env,stdin=slave,stdout=slave,stderr=slave,start_new_session=True);os.close(slave);output=bytearray()
    def drain():
        while True:
            try:output.extend(os.read(master,65536))
            except OSError:return
    threading.Thread(target=drain,daemon=True).start()
    def state():
        try:return json.loads((folder/'tt-native-test-ready.json').read_text())
        except (ValueError,OSError):return {}
    def wait(predicate):
        until=time.monotonic()+12
        while time.monotonic()<until:
            value=state()
            if predicate(value):return value
            if process.poll() is not None:
                detail='UI exited: '+output[-6000:].decode('utf-8','replace')
                error_file=folder/'tt-native-test-error'
                if error_file.is_file():detail+='\nDemo exception:\n'+error_file.read_text(encoding='utf-8')
                raise AssertionError(detail)
            time.sleep(.05)
        threads=folder/'tt-native-test-threads.txt'
        detail=str(value)
        if threads.is_file():detail+='\nThread stacks:\n'+threads.read_text(encoding='utf-8')
        raise AssertionError(detail)
    def key(text):os.write(master,text.encode());time.sleep(.15)
    def click(x,y):os.write(master,f'\x1b[<0;{x+1};{y+1}M'.encode());time.sleep(.15)
    def resize(rows,cols):
        fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack('HHHH',rows,cols,rows*16,cols*8))
        return wait(lambda s:s.get('sizes',{}).get('root')==[rows,cols])
    try:
        wait(lambda s:s.get('count')==18 and s.get('visible_chats',0)>0 and s.get('chat_list_drawn'))
        assert state()['visible_chats']==10,'chat list was not capped at ten visible rows'
        list_screenshot=folder/'artifacts'/'chat-list.png';deadline=time.monotonic()+8
        while not list_screenshot.is_file() and time.monotonic()<deadline:time.sleep(.05)
        assert list_screenshot.is_file(),'chat-list screenshot was not captured'
        for selected in range(1,13):
            key('\x1b[B');wait(lambda s:s.get('mode')=='chats' and s.get('list_index')==selected)
        assert state()['list_offset']>0,'chat list did not scroll with selection'
        for selected in range(11,-1,-1):
            key('\x1b[A');wait(lambda s:s.get('mode')=='chats' and s.get('list_index')==selected)
        chat_state=wait(lambda s:s.get('chat_rows') and s.get('chat_ids'))
        panel=chat_state['chat_rect'];row=chat_state['chat_rows'][0]
        click(panel[1]+3,row[0])
        opened=wait(lambda s:s.get('mode')=='messages' and s.get('history_count',0)>=120 and s.get('drawn_ids') and not s.get('pending'))
        assert opened['chat_ids'][row[2]]==101,'mouse click did not open the selected synthetic chat'
        key('\x1b[6;16;8t')
        opened=wait(lambda s:s.get('mode')=='messages' and s.get('history_count',0)>=120 and not s.get('pending'))
        assert opened['visible_chats']==10,'conversation sidebar did not keep ten chats visible'
        transitioned=wait(lambda s:s.get('transition_count',0)>=1 and len(s.get('transition_phases',[]))>=4)
        assert transitioned['transition_phases']==[0,1,2,3],f'chat transition did not reach all four animated states: {transitioned.get("transition_phases")}'
        assert opened['current_id']==10119,'synthetic history did not open at the newest message'
        assert opened['sizes']['messages'][1]>opened['sizes']['chats'][1]*2,'conversation did not receive the larger panel'
        assert {button[3] for button in opened['buttons']} >= {'send','document','voice'}
        assert not ({'stickers','gif_gallery','forward'} & {button[3] for button in opened['buttons']}),'composer toolbar is not contextual'
        screenshot=folder/'artifacts'/'conversation.png';deadline=time.monotonic()+8
        while not screenshot.is_file() and time.monotonic()<deadline:time.sleep(.05)
        threads=folder/'tt-native-test-threads.txt'
        stack='\n'+threads.read_text(encoding='utf-8') if threads.is_file() else ''
        report_error=folder/'tt-native-test-report-error.txt'
        detail='\nReport error:\n'+report_error.read_text(encoding='utf-8') if report_error.is_file() else ''
        assert screenshot.is_file(),'conversation screenshot was not captured: '+output[-3000:].decode('utf-8','replace')+detail+stack
        from PIL import Image,ImageChops
        with Image.open(screenshot) as image:assert image.size==(1400,810),'conversation screenshot used the wrong terminal size'
        key('\x1b[A'*88);visible=wait(lambda s:s.get('current_id')==10031)
        assert 10031 in visible['drawn_ids'],'long Unicode message left the visible history while selected'
        resize(24,80)
        compact=wait(lambda s:s.get('sizes',{}).get('root')==[24,80] and s.get('input_y',99)<24)
        assert compact['sizes']['root']==[24,80] and compact['input_y']<24,'80x24 terminal lost the composer'
        resize(40,120)
        medium=wait(lambda s:s.get('sizes',{}).get('root')==[40,120] and s.get('input_y',99)<40)
        assert medium['sizes']['root']==[40,120] and medium['input_y']<40,'120x40 terminal lost the composer'
        resize(12,70);resize(45,140)
        key('\x16');key('CAPTION');wait(lambda s:s.get('attachments',{}).get('chat:101') and s.get('buffer')=='CAPTION')
        key('\r');sent=wait(lambda s:s.get('current_id')==20001 and not s.get('pending') and s.get('buffer')=='')
        time.sleep(1);assert state()['frames']<=sent['frames']+1,'progress-only events repainted history'
        key('\x1b[A');wait(lambda s:s.get('current_id')!=20001 and not s.get('pending'))
        key('\x1b[B');wait(lambda s:s.get('current_id')==20001 and not s.get('pending'))
        key('\x0f');time.sleep(.3);key('\x1b');wait(lambda s:s.get('current_id')==20001 and not s.get('overlay') and not s.get('pending'))
        key('SAVED DRAFT');wait(lambda s:s.get('buffer')=='SAVED DRAFT')
        long_text='Тест длинного сообщения 🙂 — English / русский. '*18
        key(long_text);typed=wait(lambda s:s.get('buffer')=='SAVED DRAFT'+long_text)
        assert typed['history_count']>=120
        key('\x0c');wait(lambda s:s.get('mode')=='chats' and not s.get('pending'));key('\r');restored=wait(lambda s:s.get('mode')=='messages' and s.get('buffer')=='SAVED DRAFT'+long_text and not s.get('pending'))
        key('\x11');process.wait(timeout=5)
        assert process.returncode==0,output[-3000:]
        assert '\x1bP0;0q' in output.decode('utf-8','replace'),'no SIXEL graphics emitted'
        assert (folder/'tt-native-test-session.json').is_file()
        artifact_dir=Path(__file__).parent/'artifacts';artifact_dir.mkdir(exist_ok=True)
        demo_artifacts=folder/'artifacts'
        for name in ('chat-list.png','conversation.png'):
            source=demo_artifacts/name
            assert source.is_file(),f'missing synthetic screenshot: {name}'
            shutil.copy2(source,artifact_dir/name)
        frames=sorted((folder/'transition-frames').glob('frame-*.png'))
        for frame_path in frames:shutil.copy2(frame_path,artifact_dir/frame_path.name)
        assert len(frames)==4,f'chat reveal did not capture one frame for each of four animated states (observed {len(frames)})'
        images=[Image.open(path).convert('RGB') for path in frames]
        message_region=(330,45,1200,670)
        header_region=(330,0,1400,54)
        signatures={image.crop(message_region).tobytes() for image in images}
        header_signatures={image.crop(header_region).tobytes() for image in images}
        assert len(header_signatures)==4,f'chat reveal showed only {len(header_signatures)} distinct transition indicators'
        assert len(signatures)>=3,f'chat reveal produced only {len(signatures)} distinct message-region frames'
        distinct_changes=0;previous=None
        for image in images:
            current=image.crop(message_region)
            if previous is not None and ImageChops.difference(previous,current).getbbox():distinct_changes+=1
            previous=current
        assert distinct_changes>=2,f'chat reveal displayed only {distinct_changes} visible state changes'
        images[0].save(artifact_dir/'chat-transition.gif',save_all=True,append_images=images[1:],duration=105,loop=0,optimize=False)
        assert restored['sizes']['root']==[45,140]
        print('PASS: synthetic 120-message history, 4-state chat reveal, SGR mouse navigation, 80x24 and 120x40 resize, long Unicode draft, contextual composer, image attachment + caption, fake photo send, 100 progress updates without history repaint, scroll, settings return, draft restore, Ctrl+Q and SIXEL output')
    finally:
        if process.poll() is None:process.terminate();process.wait(timeout=5)
        os.close(master)
