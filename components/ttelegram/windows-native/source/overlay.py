"""Modal terminal windows share one curses session and suspend background drawing."""
from contextlib import contextmanager
import curses
from native_image import synchronized,clear

def run_modal(controller,callback):
    # Never call curses.wrapper/initscr/endwin inside the running TUI.
    h,w=controller.view.stdscr.getmaxyx()
    screen=curses.newwin(h,w,0,0)
    screen.keypad(True)
    try:return callback(screen)
    finally:
        screen.keypad(False)
        curses.noecho();curses.cbreak()
        controller.view.stdscr.keypad(True)
        curses.mousemask(curses.ALL_MOUSE_EVENTS)

@contextmanager
def open_overlay(controller,label,zoom=False):
    from workspace_mode import mode
    from native_image import _lock
    views=(controller.view.chats,controller.view.msgs,controller.view.status)
    with _lock:
        previous=[getattr(view,'gallery_active',False) for view in views]
        was_active=getattr(controller,'gallery_active',False)
        for view in views:view.gallery_active=True
        controller.gallery_active=True
        clear(controller.view.stdscr)
    try:
        with mode(label):yield
    finally:
        with _lock:
            clear(controller.view.stdscr)
            for view,value in zip(views,previous):view.gallery_active=value
            controller.gallery_active=was_active
            # Rebuild all windows before the next input read or TDLib redraw.
            controller._resize()


def confirm(controller,prompt):
    def run(screen):
        curses.curs_set(0);screen.timeout(200)
        while True:
            screen.erase();h,w=screen.getmaxyx()
            screen.addnstr(1,1,prompt,max(1,w-2))
            screen.addnstr(3,1,'Enter — подтвердить · Esc — отменить',max(1,w-2));screen.refresh()
            try:key=screen.get_wch()
            except curses.error:continue
            if key in ('\n','\r',curses.KEY_ENTER):return True
            if key=='\x1b':return False
            if key in ('\x11','\x0c'):
                controller.view.status.pending_action='quit' if key=='\x11' else 'chat_list';return False
    return run_modal(controller,run)
