"""Synthetic PCM and fake PortAudio streams. Never opens an audio device."""
import sys,unittest,tempfile,array,math,shutil,types
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'source'))
import windows_audio as audio
class Stop(Exception):pass
class Input:
    def __init__(self,**kw):self.callback=kw['callback'];self.closed=False
    def start(self):pass
    def stop(self):pass
    def close(self):self.closed=True
class Output(Input):
    def __init__(self,**kw):super().__init__(**kw);self.finished=kw['finished_callback']
    def abort(self):self.finished()
    def pump(self,frames):
        block=bytearray(frames*2)
        try:self.callback(block,frames,None,None)
        except Stop:self.finished()
class Audio(unittest.TestCase):
    @unittest.skipUnless(shutil.which('ffmpeg'),'Needs an FFmpeg executable for synthetic codec verification')
    def test_silence_tone_playback_toggle_and_draft(self):
        fake=types.SimpleNamespace(RawInputStream=Input,RawOutputStream=Output,CallbackStop=Stop)
        with tempfile.TemporaryDirectory(prefix='Telegram голос ') as d,patch.dict(sys.modules,{'sounddevice':fake}),patch.object(audio.Path,'home',return_value=Path(d)),patch.object(audio,'ffmpeg',return_value=shutil.which('ffmpeg')):
            voice=audio.InlineVoice(None);voice.start()
            voice.input.callback(bytes(4800*2),4800,None,None);self.assertEqual(voice.levels[-1],0)
            tone=array.array('h',(int(12000*math.sin(i*2*math.pi*440/48000)) for i in range(4800))).tobytes()
            for _ in range(9):voice.input.callback(tone,4800,None,None)
            self.assertGreater(voice.levels[-1],0);voice.stop();self.assertEqual(voice.state,'review');self.assertTrue(voice.path.stat().st_size)
            voice.play();voice.output.pump(4800);self.assertGreater(voice.progress,0);self.assertLess(voice.progress,1)
            voice.play();self.assertFalse(voice.playing);voice.play();self.assertEqual(voice.progress,0)
            voice.output.pump(96000);self.assertFalse(voice.playing);self.assertEqual(voice.progress,1)
            item=voice.draft();path=voice.path;voice.close();self.assertTrue(path.exists())
            restored=audio.InlineVoice.restore(None,item);self.assertEqual(restored.state,'review');restored.keep=False;restored.close();self.assertFalse(path.exists())
if __name__=='__main__':unittest.main()
