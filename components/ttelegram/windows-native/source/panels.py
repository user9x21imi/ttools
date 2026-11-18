"""Thin labelled containers; content windows live inside, never under borders."""
import curses
from tg.colors import get_color,cyan,bold
from tg.utils import truncate_to_len

def draw(screen,title,refresh=True):
    h,w=screen.getmaxyx();screen.erase()
    if h<2 or w<4:return
    color=get_color(cyan,-1)
    screen.addstr(0,0,'╭'+'─'*(w-2)+'╮',color)
    for row in range(1,h-1):
        screen.addstr(row,0,'│',color|curses.A_DIM)
        screen.addstr(row,w-1,'│',color|curses.A_DIM)
    screen.insstr(h-1,0,'╰'+'─'*(w-2)+'╯',color)
    screen.addstr(0,2,truncate_to_len(' '+title+' ',w-5),color|bold)
    if refresh:screen.leaveok(True);screen.redrawwin();screen.refresh()
