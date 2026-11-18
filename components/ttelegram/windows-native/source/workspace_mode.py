"""Small, persistent mode labels in each tmux pane's top border."""
from contextlib import contextmanager
from functools import wraps
import os
import subprocess

_current='Telegram / вход'

def set_mode(label):
    global _current
    if label==_current: return
    _current=label
    pane=os.environ.get('TMUX_PANE')
    if not pane or not os.environ.get('TMUX'): return
    try:
        subprocess.run(['tmux','set-option','-p','-t',pane,'@ttelegram_mode',label],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=1)
    except (OSError,subprocess.SubprocessError): pass

@contextmanager
def mode(label):
    previous=_current
    set_mode(label)
    try: yield
    finally: set_mode(previous)


def border_format():
    # Detect external tools even when an older client process has not been restarted.
    fallback='#{?@ttelegram_mode,#{@ttelegram_mode},Telegram / запуск}'
    cases=[
        ('#{m:*vim*,#{pane_current_command}}','Редактор Vim · Esc, :q, Enter — назад'),
        ('#{==:#{pane_current_command},vi}','Редактор Vi · Esc, :q, Enter — назад'),
        ('#{==:#{pane_current_command},less}','Просмотр текста · q — назад'),
        ('#{==:#{pane_current_command},ffplay}','Воспроизведение · q — остановить'),
        ('#{==:#{pane_current_command},ffmpeg}','Запись / обработка аудио'),
    ]
    label=fallback
    for condition,text in reversed(cases): label='#{?'+condition+','+text.replace(',','，')+','+label+'}'
    return '#[bold,fg=#3390ec] ● TELEGRAM #[nobold,nodim,fg=#67e8f9] / '+label+'  #[default]'


def install_handlers():
    from tg.controllers import msg_handler,chat_handler
    labels={
        'v':'Запись голосового сообщения','t':'Выбор стикера','f':'Пересылка: выбор чата',
        'r':'Ответ на сообщение','R':'Ответ в редакторе','I':'Редактор длинного сообщения',
        'A':'Редактор длинного сообщения','?':'Справка по клавишам','/':'Поиск чата',
        'S':'Выбор файла','sd':'Отправка документа','sp':'Отправка изображения',
        'sa':'Отправка аудио','sv':'Отправка видео','e':'Редактирование сообщения',
        'c':'Информация о чате','u':'Профиль пользователя','l':'Просмотр сообщения / вложения',
    }
    def wrap(fun,label):
        @wraps(fun)
        def action(*args,**kwargs):
            with mode(label): return fun(*args,**kwargs)
        return action
    for key,label in labels.items():
        if key in msg_handler: msg_handler[key]=wrap(msg_handler[key],label)
    for key,label in [('?', 'Справка по клавишам'),('/', 'Поиск чата'),('c','Контакты')]:
        if key in chat_handler: chat_handler[key]=wrap(chat_handler[key],label)
