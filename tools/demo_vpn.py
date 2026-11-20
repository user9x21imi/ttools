"""Offline TVPN view: real UI and globe, no network backend or tunnel."""
import curses
import importlib.util
from pathlib import Path
import sys
import time
from types import SimpleNamespace
source=Path(__file__).resolve().parents[1]/'components/tvpn/source'
sys.path.insert(0,str(source))
spec=importlib.util.spec_from_file_location('tvpn_preview',source/'riseup-panel.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
def main(screen):
    curses.start_color();curses.use_default_colors();curses.curs_set(0)
    for n,color in enumerate((135,78,203,221,252,242),1):curses.init_pair(n,color,-1)
    curses.init_pair(7,141 if curses.COLORS>=256 else curses.COLOR_MAGENTA,-1)
    model=module.Model();model.art='unicode';model.detail='Обзор карты · без VPN-подключения';model.ip='DEMO / NO TUNNEL';model.region='Нидерланды';model.gateway='—';model.interface='—';model.state='preview';module.LABELS['preview']='ОБЗОР КАРТЫ'
    model.globe=SimpleNamespace(box=None,zoom=1.,latitude=25.,longitude=0.,select=lambda *args:None,tick=lambda:None)
    screen.timeout(100)
    while True:
        model.globe.longitude=time.monotonic()*6%360
        module.draw(screen,model,False,True)
        if screen.getch() in (ord('q'),27):break
if __name__=='__main__':curses.wrapper(main)
