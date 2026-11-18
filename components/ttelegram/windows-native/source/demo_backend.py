"""Run an isolated synthetic account, without TDLib or microphone use."""
import os,tempfile,runpy
from pathlib import Path

def run_demo():
    os.environ['TTELEGRAM_DEMO_DIR']=tempfile.mkdtemp(prefix='ttelegram-demo-')
    runpy.run_path(str(Path(__file__).with_name('demo_scenario.py')),run_name='__main__',init_globals={'demo_path':lambda name:Path(os.environ['TTELEGRAM_DEMO_DIR'])/name})
