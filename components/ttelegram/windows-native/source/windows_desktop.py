"""Win32 clipboard/file dialogs; terminal selection for forwarding."""
import ctypes,os,tempfile,time
from pathlib import Path

def choose_file(save=False,suggested=''):
    from ctypes import wintypes as w
    class OPENFILENAME(ctypes.Structure):
        _fields_=[('lStructSize',w.DWORD),('hwndOwner',w.HWND),('hInstance',w.HINSTANCE),('lpstrFilter',w.LPCWSTR),('lpstrCustomFilter',w.LPWSTR),('nMaxCustFilter',w.DWORD),('nFilterIndex',w.DWORD),('lpstrFile',w.LPWSTR),('nMaxFile',w.DWORD),('lpstrFileTitle',w.LPWSTR),('nMaxFileTitle',w.DWORD),('lpstrInitialDir',w.LPCWSTR),('lpstrTitle',w.LPCWSTR),('Flags',w.DWORD),('nFileOffset',w.WORD),('nFileExtension',w.WORD),('lpstrDefExt',w.LPCWSTR),('lCustData',ctypes.c_ssize_t),('lpfnHook',ctypes.c_void_p),('lpTemplateName',w.LPCWSTR),('pvReserved',ctypes.c_void_p),('dwReserved',w.DWORD),('FlagsEx',w.DWORD)]
    dialog=ctypes.WinDLL('comdlg32',use_last_error=True);filename=ctypes.create_unicode_buffer(32768);filename.value=suggested
    params=OPENFILENAME();params.lStructSize=ctypes.sizeof(params);params.lpstrFilter='Все файлы\0*.*\0\0';params.lpstrFile=ctypes.cast(filename,w.LPWSTR);params.nMaxFile=32768;params.lpstrTitle='Telegram — сохранить файл' if save else 'Telegram — прикрепить файл';params.Flags=0x80000|0x800|(2 if save else 0x1000)
    function=dialog.GetSaveFileNameW if save else dialog.GetOpenFileNameW;function.argtypes=[ctypes.POINTER(OPENFILENAME)];function.restype=w.BOOL
    return filename.value if function(ctypes.byref(params)) else None

def clipboard():
    from PIL import Image,ImageGrab
    value=ImageGrab.grabclipboard()
    if isinstance(value,Image.Image):
        folder=Path.home()/'.cache/ttelegram/clipboard';folder.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix='.png',dir=folder,delete=False) as file:path=file.name
        value.save(path,'PNG');return {'kind':'image','path':path,'owned':True,'width':value.width,'height':value.height}
    if isinstance(value,list):
        from attachments import item_for
        return {'kind':'files','items':[item_for(path) for path in value if Path(path).is_file()]}
    from ctypes import wintypes as w
    user=ctypes.WinDLL('user32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    user.GetClipboardData.argtypes=[w.UINT];user.GetClipboardData.restype=w.HANDLE;kernel.GlobalLock.argtypes=[w.HGLOBAL];kernel.GlobalLock.restype=ctypes.c_void_p;kernel.GlobalUnlock.argtypes=[w.HGLOBAL]
    for _ in range(4):
        if user.OpenClipboard(None):break
        time.sleep(.03)
    else:raise ValueError('Буфер занят другой программой. Повторите вставку.')
    try:
        handle=user.GetClipboardData(13)
        if not handle:return {'kind':'empty'}
        pointer=kernel.GlobalLock(handle)
        if not pointer:return {'kind':'empty'}
        try:return {'kind':'text','text':ctypes.wstring_at(pointer)}
        finally:kernel.GlobalUnlock(handle)
    finally:user.CloseClipboard()

def choose_item(title,items,label):
    import curses
    from overlay import run_modal
    from recovery import CURRENT
    def run(screen):
        selected=0;query='';screen.timeout(100)
        while True:
            h,w=screen.getmaxyx();screen.erase();filtered=[item for item in items if query.casefold() in label(item).casefold()];selected=min(selected,max(0,len(filtered)-1));top=max(0,selected-(h-7))
            screen.addnstr(0,1,title,w-2);screen.addnstr(1,1,'Поиск: '+query,w-2)
            for index,item in enumerate(filtered[top:top+h-5],top):screen.addnstr(3+index-top,1,('› ' if index==selected else '  ')+label(item),w-2,curses.A_REVERSE if index==selected else 0)
            screen.refresh()
            try:key=screen.get_wch()
            except curses.error:continue
            if key=='\x1b':return None
            if key in ('\n','\r',curses.KEY_ENTER):return filtered[selected] if filtered else None
            if key==curses.KEY_UP:selected=max(0,selected-1)
            elif key==curses.KEY_DOWN:selected=min(len(filtered)-1,selected+1)
            elif key in ('\b','\x7f',curses.KEY_BACKSPACE):query=query[:-1];selected=0
            elif isinstance(key,str) and key.isprintable():query+=key;selected=0
    return run_modal(CURRENT,run)

def copy_text(text):
    from ctypes import wintypes as w
    user=ctypes.WinDLL('user32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GlobalAlloc.argtypes=[w.UINT,ctypes.c_size_t];kernel.GlobalAlloc.restype=w.HGLOBAL
    kernel.GlobalLock.argtypes=[w.HGLOBAL];kernel.GlobalLock.restype=ctypes.c_void_p
    kernel.GlobalUnlock.argtypes=[w.HGLOBAL];kernel.GlobalFree.argtypes=[w.HGLOBAL]
    user.SetClipboardData.argtypes=[w.UINT,w.HANDLE];user.SetClipboardData.restype=w.HANDLE
    data=(text+'\0').encode('utf-16-le');handle=kernel.GlobalAlloc(0x42,len(data))
    if not handle:raise OSError('Clipboard allocation failed')
    pointer=kernel.GlobalLock(handle)
    if not pointer:kernel.GlobalFree(handle);raise OSError('Clipboard lock failed')
    ctypes.memmove(pointer,data,len(data));kernel.GlobalUnlock(handle);transferred=False
    try:
        if not user.OpenClipboard(None):raise OSError('Clipboard is busy')
        try:
            if not user.EmptyClipboard() or not user.SetClipboardData(13,handle):raise OSError('Cannot write clipboard')
            transferred=True
        finally:user.CloseClipboard()
    finally:
        if not transferred:kernel.GlobalFree(handle)
