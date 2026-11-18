import datetime as dt
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from tthings.metrics import parse_cpu,parse_mem,parse_net,parse_disks,delta_rates,unescape_mount
from tthings.journals import Journal
from tthings.storage import StorageScan
from tthings.system_ui import calendar_lines,move_month,render_monitor

class CounterTests(unittest.TestCase):
    def test_cpu_guest_already_counted(self):
        cpu=parse_cpu('cpu 100 2 10 300 5 1 2 3 70 1\ncpu0 20 0 0 80 0 0 0 0\n')
        self.assertEqual(cpu['cpu'],(423,305))
    def test_memory_and_swap(self):
        memory=parse_mem('MemTotal: 1000 kB\nMemAvailable: 300 kB\nSwapTotal: 100 kB\nSwapFree: 80 kB\n')
        self.assertEqual(memory['used'],700*1024);self.assertEqual(memory['percent'],70);self.assertEqual(memory['swap_used'],20*1024)
    def test_network_field_positions(self):
        values=parse_net(' wlan0: 1000 2 3 4 0 0 0 0 2000 5 6 7 0 0 0 0\n')['wlan0']
        self.assertEqual(values['rx_bytes'],1000);self.assertEqual(values['tx_bytes'],2000);self.assertEqual(values['tx_drops'],7)
    def test_whole_disks_and_sector_size(self):
        text='259 0 nvme0n1 10 0 100 40 20 0 200 50 2 600 700\n259 1 nvme0n1p1 1 0 1 1 1 0 2 2 0 3 4\n'
        disks=parse_disks(text,{'nvme0n1'})
        self.assertEqual(set(disks),{'nvme0n1'});self.assertEqual(disks['nvme0n1']['read_bytes'],51200);self.assertEqual(disks['nvme0n1']['busy_ms'],600)
    def test_rate_first_sample_reset_and_real_elapsed(self):
        self.assertIsNone(delta_rates({'x':30},None,1,['x'])['x'])
        self.assertEqual(delta_rates({'x':30},{'x':10},2,['x'])['x'],10)
        self.assertIsNone(delta_rates({'x':3},{'x':10},2,['x'])['x'])
    def test_mount_escaping(self):self.assertEqual(unescape_mount('/run/My\\040Disk'),'/run/My Disk')

class JournalTests(unittest.TestCase):
    def test_rotation_and_separate_kinds(self):
        with tempfile.TemporaryDirectory() as temp:
            journal=Journal('network',temp,max_bytes=180)
            sample={'timestamp':'2026-11-17T00:00:00Z','network':{'lo':{'rx_bytes':1}}}
            for i in range(15):sample['network']['lo']['rx_bytes']=i;journal.append(sample)
            self.assertEqual(journal.tail()[-1]['network']['lo']['rx_bytes'],14)
            self.assertLessEqual(len(list(Path(temp).glob('*.jsonl*'))),4)
            self.assertFalse((Path(temp)/'performance.jsonl').exists())
            self.assertEqual(journal.tail()[-1]['schema_version'],1)

class StorageTests(unittest.TestCase):
    @unittest.skipUnless(__import__("os").name=="posix", "POSIX link and allocated-block semantics")
    def test_scan_read_only_links_and_hardlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);(base/'folder').mkdir();file=base/'folder/file';file.write_bytes(b'x'*10000)
            (base/'escape').symlink_to('/proc');(base/'alias').symlink_to(file)
            import os
            os.link(file,base/'hardlink')
            scan=StorageScan(base);scan.start();scan.thread.join(timeout=4)
            state=scan.snapshot();self.assertTrue(state['done']);self.assertIsNone(state['error'])
            self.assertNotIn('escape',dict(state['rows']));self.assertNotIn('alias',dict(state['rows']))
            expected=file.stat().st_blocks*512+(base/'folder').stat().st_blocks*512
            self.assertEqual(sum(size for _,size in state['rows']),expected)
            self.assertEqual(file.stat().st_size,10000)

class CalendarTests(unittest.TestCase):
    def test_leap_year_and_year_rollover(self):
        self.assertTrue(any('29' in line for line in calendar_lines(2024,2)))
        self.assertFalse(any('29' in line for line in calendar_lines(2025,2)))
        self.assertEqual(move_month(2026,12,1),(2027,1));self.assertEqual(move_month(2026,1,-1),(2025,12))

if __name__=='__main__':unittest.main()
