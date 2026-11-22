import unittest
import time
from ttools.visuals.effects import Frame
from unittest.mock import patch,Mock
from ttools.backgrounds import Background
from ttools.__main__ import UI,ascii_status,layout_for
class BackgroundTests(unittest.TestCase):
    def test_terminal_theme_is_not_replaced(self):
        ui=UI.__new__(UI)
        class Screen:
            def bkgd(self,*args):pass
        ui.s=Screen();pairs=[]
        with patch('curses.start_color'),patch('curses.use_default_colors'),patch('curses.COLORS',256,create=True),patch('curses.init_pair',side_effect=lambda number,fg,bg:pairs.append((number,fg,bg))),patch('curses.color_pair',return_value=0):
            ui.colors()
        self.assertTrue(pairs)
        self.assertTrue(all(bg==-1 for _,_,bg in pairs))
        self.assertIn((1,-1,-1),pairs)
        self.assertEqual({number for number,_,_ in pairs},set(range(1,21))|set(range(32,56)))

    def test_artwork_right_of_menu_has_no_missing_horizontal_rows(self):
        class Screen:
            def getmaxyx(self):return (50,120)
            def erase(self):pass
            def refresh(self):pass
            def addnstr(self,*args):pass
        class BackgroundFixture:
            effect='phyllotaxis';secondary='rose';paused=False
            MAX_WIDTH=180;MAX_HEIGHT=72;FRAME_INTERVAL=.1
            def render(self,width,height,now):
                frame=Frame(width,height)
                for y in range(4,15):frame.cells[y][width-1]=('X','primary')
                return frame
        ui=UI.__new__(UI);ui.s=Screen();ui.apps=[];ui.errors=[]
        ui.selected=0;ui.query='';ui.searching=False;ui.status='';ui.updates={};ui.jobs={}
        ui.last_check=time.monotonic();ui.started=0;ui.splash=False;ui.background=BackgroundFixture()
        ui.motion_enabled=False;ui.ascii_mode=False;ui.help_open=False;ui.launching=None;ui.return_started=None
        ui.selection_from=0;ui.selection_started=0;ui.selection_duration=.12
        with patch('curses.color_pair',side_effect=lambda n:n):ui.draw()
        geometry=layout_for(120,50)
        for y in range(10,21):self.assertEqual(ui._pending[(y,geometry['art_x']+geometry['art_width']-1)][0],'X')

    def test_enter_dismisses_splash_without_launching_app(self):
        ui=UI.__new__(UI);ui.s=Mock();ui.s.get_wch.side_effect=['\n','q']
        ui.draw=Mock();ui.pool=Mock();ui.launch=Mock()
        ui.splash=True;ui.started=time.monotonic();ui.searching=False
        ui.run()
        self.assertFalse(ui.splash)
        ui.launch.assert_not_called()

    def test_pause_preserves_frame_and_resume_advances_time(self):
        bg=Background(seed=4,now=0)
        frame=bg.render(80,24,1)
        bg.toggle(1)
        self.assertIs(bg.render(80,24,600),frame)
        self.assertEqual(bg.logical,1)
        bg.toggle(600)
        self.assertIsNot(bg.render(80,24,601),frame)
        self.assertEqual(bg.logical,2)
    def test_rate_limit_resize_and_two_layer_palette(self):
        bg=Background(seed=1,now=0)
        frame=bg.render(80,24,1)
        self.assertIs(bg.render(80,24,1.02),frame)
        self.assertEqual({c for row in frame.cells for ch,c in row if ch!=' '},{'primary','secondary'})
        large=bg.render(9999,9999,2)
        self.assertEqual((large.w,large.h),(180,72))
        tiny=bg.render(0,0,3)
        self.assertEqual((tiny.w,tiny.h),(1,1))
    def test_manual_switch_while_paused_and_transition_resize(self):
        bg=Background(seed=8,now=0,motion=False)
        old=bg.effect;bg.render(80,24,0);bg.change(3)
        self.assertNotEqual(bg.effect,old)
        frame=bg.render(80,24,50)
        self.assertIs(bg.render(80,24,100),frame)
        bg.toggle(100);bg.change(101);bg.render(10,10,101.1)
        self.assertEqual(bg.size,(10,10))
    def test_low_power_caps_area_and_frame_rate(self):
        bg=Background(seed=1,now=0,low_power=True)
        frame=bg.render(300,100,0)
        self.assertEqual((frame.w,frame.h),(96,32))
        self.assertIs(bg.render(300,100,.24),frame)
        self.assertIsNot(bg.render(300,100,.26),frame)

    def test_unchanged_ui_cells_are_not_written_again(self):
        class Screen:
            def __init__(self):self.writes=[];self.refreshes=0
            def addnstr(self,*args):self.writes.append(args)
            def refresh(self):self.refreshes+=1
        ui=UI.__new__(UI);ui.s=Screen();ui._pending={(0,0):('A',1,False)}
        with patch('curses.color_pair',return_value=1):
            ui.flush();self.assertEqual(len(ui.s.writes),1)
            ui.flush();self.assertEqual(len(ui.s.writes),1)
            self.assertEqual(ui.s.refreshes,1)
            ui._pending={};ui.flush()
            self.assertEqual(ui.s.writes[-1][2],' ')
            self.assertEqual(ui.s.refreshes,2)

    def test_responsive_layout_keeps_all_five_apps_at_reference_sizes(self):
        apps=[{'id':name,'name':name,'command':['/usr/bin/true']} for name in ('tspotify','tsoundcloud','ttelegram','tvpn','tthings')]
        class Screen:
            def __init__(self,w,h):self.w=w;self.h=h;self.cells={}
            def getmaxyx(self):return self.h,self.w
            def erase(self):self.cells={}
            def refresh(self):pass
            def addnstr(self,y,x,text,n,style):
                for off,char in enumerate(text[:n]):self.cells[(y,x+off)]=char
        for width,height in ((80,24),(120,40),(160,50)):
            ui=UI.__new__(UI);ui.s=Screen(width,height);ui.apps=apps;ui.errors=[];ui.selected=0;ui.query='';ui.searching=False
            ui.status='Ready';ui.updates={};ui.jobs={};ui.last_check=time.monotonic();ui.started=0;ui.splash=False
            ui.background=Background(seed=3,motion=False);ui.background.set_accent('spotify',0,animate=False)
            ui.motion_enabled=False;ui.ascii_mode=False;ui.help_open=False;ui.launching=None;ui.return_started=None
            ui.selection_from=0;ui.selection_started=0;ui.selection_duration=.12;ui._paint_cache={}
            with patch('curses.color_pair',side_effect=lambda n:n):ui.draw()
            text=''.join(ui.s.cells.values())
            for app in apps:self.assertIn(app['name'],text,(width,height,app['name']))
            self.assertEqual(len(ui.visible),5)
            self.assertEqual(layout_for(width,height)['wide'],width>=116 and height>=30)
            if width>=116:self.assertTrue(any(0x2800<=ord(char)<=0x28ff for char in text))

    def test_selection_transition_is_120ms_and_new_input_retargets(self):
        ui=UI.__new__(UI);ui.apps=[{'id':name,'name':name,'command':['/usr/bin/true']} for name in ('tspotify','tsoundcloud','ttelegram')]
        ui.query='';ui.selected=0;ui.motion_enabled=True;ui.selection_from=0.;ui.selection_started=10.;ui.selection_duration=.12
        ui.background=Background(seed=4,now=0)
        ui.select(1,10.)
        self.assertEqual(ui.selection_position(10.),0.)
        middle=ui.selection_position(10.06)
        self.assertGreater(middle,0.4);self.assertLess(middle,0.6)
        ui.select(2,10.06)
        self.assertAlmostEqual(ui.selection_position(10.06),middle)
        self.assertEqual(ui.selection_position(10.18),2.)

    def test_art_accent_transition_reuses_cached_glyph_frame(self):
        bg=Background(seed=5,now=0,motion=False)
        frame=bg.render(80,24,1)
        bg.set_accent('telegram',1,animate=True)
        self.assertIs(bg.render(80,24,1.04),frame)
        old,new,mix=bg.accent_mix(1.0)
        self.assertEqual((old,new,mix),('things','telegram',0.))
        self.assertAlmostEqual(bg.accent_mix(1.06)[2],.5,places=2)
        self.assertEqual(bg.accent_mix(1.12)[2],1.)

    def test_ascii_graphics_fallback_emits_only_ascii(self):
        ui=UI.__new__(UI);ui.ascii_mode=True
        result=''.join(ui._display_glyph(chr(value)) for value in (0x2800,0x2803,0x28ff))
        self.assertTrue(result.isascii())
        self.assertEqual(ascii_status('Готово к запуску'),'Ready to launch')

    def test_auto_splash_expiry_stops_fast_polling(self):
        ui=UI.__new__(UI);ui.splash=True;ui.started=0;ui.motion_enabled=False
        ui.jobs={};ui.background=Background(seed=1,motion=False)
        self.assertEqual(ui._timeout(2),60000)
        self.assertFalse(ui.splash)

    def test_hidden_art_does_not_keep_small_terminal_awake(self):
        class Screen:
            def __init__(self,size):self.size=size
            def getmaxyx(self):return self.size
        ui=UI.__new__(UI);ui.s=Screen((24,80));ui.splash=False;ui.motion_enabled=True
        ui.selection_started=0;ui.selection_duration=.12;ui.return_started=None;ui.help_open=False
        ui.background=Background(seed=1,now=0,motion=True);ui.jobs={}
        self.assertEqual(ui._timeout(10),60000)
        ui.s=Screen((40,120))
        self.assertEqual(ui._timeout(10),100)

    def test_no_motion_makes_selection_instant(self):
        ui=UI.__new__(UI);ui.apps=[{'id':'tspotify'},{'id':'tsoundcloud'}];ui.query='';ui.selected=0
        ui.motion_enabled=False;ui.background=Background(seed=2,now=0,motion=False)
        ui.select(1,now=1)
        self.assertEqual(ui.selection_position(1),1.)
        ui.toggle_motion()
        self.assertTrue(ui.background.paused)
if __name__=='__main__':unittest.main()
