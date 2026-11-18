"""Exercise the registered widget handlers without a desktop display."""
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

class Widget:
    widgets=[]
    def __init__(self,*args,**kwargs):
        self.bindings={};self.options=dict(kwargs);self.alive=True;self.widgets.append(self)
    def bind(self,sequence,callback,**kwargs):self.bindings[sequence]=callback
    def unbind(self,sequence):self.bindings.pop(sequence,None)
    def pack(self,**kwargs):pass
    def configure(self,**kwargs):self.options.update(kwargs)
    def destroy(self):self.alive=False
    def winfo_width(self):return 640
    def winfo_height(self):return 300
    def winfo_x(self):return 0
    def winfo_y(self):return 0
    def focus_set(self):pass
    def focus_force(self):pass
    def delete(self,*args):pass
    def insert(self,*args):pass
    def tag_configure(self,*args,**kwargs):pass
    def add_command(self,**kwargs):pass
    def add_separator(self):pass

class Root(Widget):
    instance=None;scenario=None
    def __init__(self):
        super().__init__();Root.instance=self;self.callbacks={};self.sequence=0;self.current_title='';self.tk=SimpleNamespace(call=lambda *args:'x11')
    def title(self,value):self.current_title=value
    def withdraw(self):pass
    def overrideredirect(self,*args):pass
    def attributes(self,*args):pass
    def winfo_children(self):return []
    def geometry(self,*args):pass
    def minsize(self,*args):pass
    def deiconify(self):pass
    def lift(self):pass
    def winfo_exists(self):return self.alive
    def focus_displayof(self):return self
    def after(self,ms,callback):self.sequence+=1;self.callbacks[self.sequence]=(ms,callback);return self.sequence
    def after_cancel(self,id):self.callbacks.pop(id,None)
    def mainloop(self):Root.scenario(self)
    def run_callback(self,name):
        for id,(ms,callback) in list(self.callbacks.items()):
            if callback.__name__==name:self.callbacks.pop(id);callback();return
        raise AssertionError('No callback '+name)

class Font:
    def __init__(self,**kwargs):pass
    def measure(self,text):return 8
    def metrics(self,name):return 16

class GuiControlsTests(unittest.TestCase):
    def test_focused_text_next_random_cyrillic_and_two_second_hold(self):
        Widget.widgets=[];clock=[0.]
        def scenario(root):
            area=next(w for w in Widget.widgets if w.options.get('wrap')=='none')
            root.run_callback('tick');initial=root.current_title
            def press(char,keysym=None):
                return area.bindings['<KeyPress>'](SimpleNamespace(char=char,keysym=keysym or char,state=0))
            self.assertEqual(press('n'),'break');root.run_callback('tick');self.assertNotEqual(root.current_title,initial)
            self.assertIn('ДНК',root.current_title) # terrain -> dna is sequential, not random
            old=root.current_title;press('r');root.run_callback('tick');self.assertNotEqual(root.current_title,old)
            clock[0]=2.1;root.run_callback('held_random');root.run_callback('tick');self.assertIn('авто',root.current_title)
            old=root.current_title;clock[0]=33.;root.run_callback('tick');self.assertNotEqual(root.current_title.split(' · авто')[0],old.split(' · авто')[0])
            area.bindings['<KeyRelease>'](SimpleNamespace(char='r',keysym='r'));root.run_callback('clear_hold')
            old=root.current_title;press('к','Cyrillic_ka');root.run_callback('tick');self.assertNotEqual(root.current_title,old)
            self.assertEqual(press('','Escape'),'break');self.assertFalse(root.alive)
        Root.scenario=scenario
        font=SimpleNamespace(Font=Font);tk=SimpleNamespace(Tk=Root,Text=Widget,Frame=Widget,Button=Widget,Menu=Widget,font=font)
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'XDG_CACHE_HOME':temp}),patch.dict(sys.modules,{'tkinter':tk,'tkinter.font':font}),patch('tthings.gui.time.monotonic',side_effect=lambda:clock[0]),patch('tthings.playback.random.uniform',return_value=30):
            from tthings.gui import show
            show('terrain')

if __name__=='__main__':unittest.main()
