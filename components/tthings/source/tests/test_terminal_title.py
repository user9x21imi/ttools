import unittest
import os,tempfile
from pathlib import Path
from unittest.mock import patch
from tthings.terminal import Terminal

class TerminalTitleTests(unittest.TestCase):
    def test_title_prefix_updates_without_repeated_escape_sequences(self):
        term=Terminal();term.konsole=False;output=[];term.write=output.append
        term.set_title('Ландшафт');term.set_title('Ландшафт');term.set_title('Календарь')
        self.assertEqual(len(output),2)
        self.assertEqual(output[0],'\x1b]0;tthings — Ландшафт\x07')
        self.assertEqual(output[1],'\x1b]0;tthings — Календарь\x07')
    def test_no_control_character_injection(self):
        term=Terminal();term.konsole=False;output=[];term.write=output.append
        term.set_title('a\x1b]0;bad\x07\n')
        self.assertNotIn('\x1b',output[0][4:]);self.assertEqual(output[0].count('\x07'),1)

class KonsoleTitleTests(unittest.TestCase):
    def test_konsole_sets_tab_format_to_window_title(self):
        term=Terminal();term.konsole=True;out=[];term.write=out.append
        term.set_title('Часы (clock) · Beautiful Things');term.set_title('Часы (clock) · Beautiful Things')
        self.assertEqual(len(out),1)
        self.assertIn('\x1b]0;tthings — Часы (clock) · Beautiful Things\x07',out[0])
        self.assertTrue(out[0].endswith('\x1b]30;%w\x07'))
    def test_stop_restores_saved_tab_format(self):
        term=Terminal();term.konsole=True;term.active=True;term.old=None;term.previous_tab_format='%d : %n'
        out=[];term.write=out.append;term.stop()
        self.assertIn('\x1b]30;%d : %n\x07',''.join(out));self.assertIn('\x1b[23;0t',''.join(out))
    def test_profile_fallback_without_dbus(self):
        from tthings.konsole_title import previous_tab_format
        with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{'XDG_CONFIG_HOME':td,'XDG_DATA_HOME':td,'KONSOLE_DBUS_SERVICE':''}):
            Path(td,'konsole').mkdir();Path(td,'konsolerc').write_text('[Desktop Entry]\nDefaultProfile=custom.profile\n')
            Path(td,'konsole/custom.profile').write_text('[General]\nLocalTabTitleFormat=%h — %n\n')
            self.assertEqual(previous_tab_format(),'%h — %n')
    def test_activity_and_section_are_in_captions(self):
        from tthings.titles import effect_caption,system_caption
        self.assertIn('(clock) · Beautiful Things',effect_caption('clock'))
        self.assertEqual(system_caption('Процессы'),'Процессы · Systems Things')

if __name__=='__main__':unittest.main()
