import unittest
from tthings.terminal import Terminal

class TerminalTitleTests(unittest.TestCase):
    def test_title_prefix_updates_without_repeated_escape_sequences(self):
        term=Terminal();output=[];term.write=output.append
        term.set_title('Ландшафт');term.set_title('Ландшафт');term.set_title('Календарь')
        self.assertEqual(len(output),2)
        self.assertEqual(output[0],'\x1b]0;tthings — Ландшафт\x07')
        self.assertEqual(output[1],'\x1b]0;tthings — Календарь\x07')
    def test_no_control_character_injection(self):
        term=Terminal();output=[];term.write=output.append
        term.set_title('a\x1b]0;bad\x07\n')
        self.assertNotIn('\x1b',output[0][4:]);self.assertEqual(output[0].count('\x07'),1)

if __name__=='__main__':unittest.main()
