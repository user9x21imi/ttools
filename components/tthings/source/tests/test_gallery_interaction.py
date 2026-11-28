"""Deterministic Gallery Mode interaction and preview transition checks."""
import unittest
from unittest.mock import patch

from tthings.app import run
from tthings.effects import Frame
from tthings.preview import GalleryPreview


class SolidScene:
    def __init__(self,name):self.char=name[0].upper()
    def render(self,width,height,elapsed,palette=0):
        frame=Frame(width,height)
        for row in frame.cells:
            for index in range(width):row[index]=(self.char,'#ffffff')
        return frame


class ScriptedTerminal:
    def __init__(self,keys,events):self.keys=list(keys);self.events=events;self.frames=[]
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def set_title(self,title):self.events.append(('title',title))
    def size(self):return 100,28
    def draw(self,frame):
        self.events.append('draw')
        self.frames.append(frame.plain())
    def read(self,timeout):return self.keys.pop(0) if self.keys else 'q'


class IdleSystemPreview:
    worker=None
    fetch=None
    def close(self):pass


class GalleryInteractionTests(unittest.TestCase):
    def test_preview_selection_dissolves_and_survives_resize(self):
        preview=GalleryPreview(SolidScene)
        preview.select('old',0.)
        self.assertEqual(set(ch for row in preview.render(32,8,0.).plain().splitlines() for ch in row),{'O'})
        preview.select('new',1.)
        start=preview.render(32,8,1.).plain()
        self.assertEqual(set(ch for row in start.splitlines() for ch in row),{'O'})
        middle=preview.render(32,8,1.+preview.TRANSITION/2).plain()
        mid_chars={ch for row in middle.splitlines() for ch in row}
        self.assertEqual(mid_chars,{'O','N'})
        resized=preview.render(12,5,1.+preview.TRANSITION/2).plain()
        self.assertEqual((len(resized.splitlines()),len(resized.splitlines()[0])),(5,12))
        end=preview.render(12,5,1.+preview.TRANSITION).plain()
        self.assertEqual(set(ch for row in end.splitlines() for ch in row),{'N'})
        self.assertIsNone(preview.outgoing)

    def test_gallery_category_search_favorites_effect_launch_and_return(self):
        events=[]
        terminal=ScriptedTerminal(
            ['down','tab','tab','2','л','а','в','а','enter','*','f','enter','escape'],events)
        saved=[]
        with patch('tthings.app.Terminal',return_value=terminal), \
             patch('tthings.app.read',return_value={'palette':0,'favorites':[]}), \
             patch('tthings.app.save',side_effect=saved.append), \
             patch('tthings.app.play',side_effect=lambda term,name,palette:events.append(('play',name))), \
             patch('tthings.system_preview.SystemPreview',IdleSystemPreview):
            run()

        self.assertIn(('title','Gallery Mode · Beautiful Things'),events)
        self.assertTrue(any('Tab: Абстракции' in frame for frame in terminal.frames))
        self.assertTrue(any('Лавовая лампа' in frame for frame in terminal.frames))
        self.assertTrue(any('› * Лавовая лампа' in frame for frame in terminal.frames))
        self.assertEqual([event for event in events if isinstance(event,tuple) and event[0]=='play'],[('play','lava')])
        play_index=events.index(('play','lava'))
        self.assertIn('draw',events[play_index+1:])  # Menu rendered again after effect return.
        self.assertEqual(saved[-1]['favorites'],['lava'])


if __name__=='__main__':unittest.main()
