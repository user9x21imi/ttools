"""Context-specific help: each shortcut appears once, next to its window."""
import curses
from tg.colors import get_color,cyan,bold

def lines(mode):
    shared=[('ВЕЗДЕ',''),('Ctrl+L','Список чатов'),('Ctrl+O','Настройки'),('Ctrl+Q','Сохранить и выйти'),('Ctrl+R','Обновить данные'),('F1','Эта справка')]
    chats=[('СПИСОК ЧАТОВ',''),('↑ / ↓ / колесо','Выбрать чат'),('Enter / клик','Открыть выбранный чат'),('Печатать / Ctrl+F','Поиск по названиям'),('Esc','Очистить поиск')]
    messages=[('ПЕРЕПИСКА — ВВОД',''),('Печатать','Написать сообщение'),('Enter','Отправить написанное'),('Ctrl+V','Вставить текст или файлы'),('Ctrl+U / перетащить','Прикрепить файл'),('Ctrl+G','Голосовое: начать запись'),('Ctrl+T','Стикеры и GIF'),('PgUp / PgDn','Прокрутить историю'),('Tab','Переключить ввод / выделение'),('Esc','Вернуться к списку чатов'),('Клик по медиа','Открыть на всё окно')]
    selection=[('ПЕРЕПИСКА — ВЫДЕЛЕНИЕ',''),('↑ / ↓','Выбрать сообщение'),('Пробел','Выделить для пересылки'),('Tab / клик по вводу','Продолжить писать'),('Кнопки Ответ / Пересл.','Действия с выбранным')]
    voice=[('ГОЛОСОВОЕ',''),('Ctrl+G / кнопка','Начать запись из переписки'),('Ctrl+G ещё раз','Остановить запись'),('Enter','Отправить запись'),('P','Прослушать / остановить; повторяемо'),('Esc','Отменить и вернуться')]
    return shared+[('','')]+(chats if mode=='chats' else messages+[('','')]+selection)+[('','')]+voice

def show(controller):
    from overlay import open_overlay,run_modal
    content=lines(controller.view_mode)
    def run(screen):
        curses.curs_set(0);screen.keypad(True);screen.timeout(200);offset=0
        while True:
            h,w=screen.getmaxyx();screen.erase();screen.redrawwin()
            accent=get_color(cyan,-1)|bold
            screen.addstr(0,2,'ПОДСКАЗКИ / '+('СПИСОК ЧАТОВ' if controller.view_mode=='chats' else 'ПЕРЕПИСКА'),accent)
            screen.addstr(1,2,'F1 / Esc — закрыть. ↑↓ / колесо — прокрутить. F4 и F7 — дополнительные алиасы.'[:max(1,w-4)])
            visible=max(1,h-5)
            for row,(key,label) in enumerate(content[offset:offset+visible],3):
                text=(key if not label else f'{key:<24} {label}')[:max(1,w-4)]
                screen.addstr(row,2,text,accent if not label else 0)
            screen.refresh()
            try:key=screen.get_wch()
            except curses.error:continue
            if key in ('\x1b',curses.KEY_F1):return
            if key=='\x0c':controller.view.status.pending_action='chat_list';return
            if key=='\x0f':controller.view.status.pending_action='settings';return
            if key=='\x11':controller.view.status.pending_action='quit';return
            if key in (curses.KEY_DOWN,curses.KEY_NPAGE):offset=min(max(0,len(content)-visible),offset+(visible if key==curses.KEY_NPAGE else 1))
            elif key in (curses.KEY_UP,curses.KEY_PPAGE):offset=max(0,offset-(visible if key==curses.KEY_PPAGE else 1))
            elif key==curses.KEY_MOUSE:
                try:_,x,y,_,buttons=curses.getmouse()
                except curses.error:continue
                if buttons&getattr(curses,'BUTTON4_PRESSED',0):offset=max(0,offset-3)
                elif buttons&getattr(curses,'BUTTON5_PRESSED',0):offset=min(max(0,len(content)-visible),offset+3)
    with open_overlay(controller,'Подсказки текущего экрана · F1/Esc — закрыть'):run_modal(controller,run)
