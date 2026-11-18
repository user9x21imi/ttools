"""Native hotkey adapters. Wayland bindings belong to the compositor."""
import ctypes
import os
import sys
from .app import spawn_window

def listen():
    if os.name=='nt':
        from ctypes import wintypes
        user=ctypes.windll.user32
        if not user.RegisterHotKey(None,1,0x4000|0x0001|0x0008,ord('G')):
            raise RuntimeError('Win+Alt+G уже занято или недоступно')
        if not user.RegisterHotKey(None,2,0x4000|0x0001|0x0008|0x0002,ord('G')):
            user.UnregisterHotKey(None,1)
            raise RuntimeError('Ctrl+Win+Alt+G уже занято или недоступно')
        msg=wintypes.MSG()
        try:
            while user.GetMessageW(ctypes.byref(msg),None,0,0)>0:
                if msg.message==0x0312:spawn_window(True,snap=msg.wParam==2)
        finally:
            user.UnregisterHotKey(None,1);user.UnregisterHotKey(None,2)
    elif sys.platform=='darwin':
        from ctypes.util import find_library
        carbon=ctypes.CDLL(find_library('Carbon'))
        class HotKeyID(ctypes.Structure):_fields_=[('signature',ctypes.c_uint32),('id',ctypes.c_uint32)]
        class EventType(ctypes.Structure):_fields_=[('eventClass',ctypes.c_uint32),('eventKind',ctypes.c_uint32)]
        callback_type=ctypes.CFUNCTYPE(ctypes.c_int32,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p)
        carbon.GetEventParameter.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_void_p]
        def handler(a,b,c):
            hotkey=HotKeyID()
            status=carbon.GetEventParameter(b,int.from_bytes(b'----','big'),int.from_bytes(b'hkid','big'),None,ctypes.sizeof(hotkey),None,ctypes.byref(hotkey))
            if status==0:spawn_window(True,snap=hotkey.id==2)
            return 0
        callback=callback_type(handler)
        carbon.GetApplicationEventTarget.restype=ctypes.c_void_p
        target=carbon.GetApplicationEventTarget()
        carbon.InstallEventHandler.argtypes=[ctypes.c_void_p,callback_type,ctypes.c_uint32,ctypes.POINTER(EventType),ctypes.c_void_p,ctypes.c_void_p]
        event=EventType(int.from_bytes(b'keyb','big'),6)
        status=carbon.InstallEventHandler(target,callback,1,ctypes.byref(event),None,None)
        if status:raise RuntimeError(f'InstallEventHandler: {status}')
        carbon.RegisterEventHotKey.argtypes=[ctypes.c_uint32,ctypes.c_uint32,HotKeyID,ctypes.c_void_p,ctypes.c_uint32,ctypes.POINTER(ctypes.c_void_p)]
        ref=ctypes.c_void_p()
        status=carbon.RegisterEventHotKey(5,(1<<8)|(1<<11),HotKeyID(0x54475244,1),target,0,ctypes.byref(ref))
        if status:raise RuntimeError(f'Cmd+Option+G недоступно: {status}')
        snapref=ctypes.c_void_p()
        status=carbon.RegisterEventHotKey(5,(1<<8)|(1<<11)|(1<<12),HotKeyID(0x54475244,2),target,0,ctypes.byref(snapref))
        if status:
            carbon.UnregisterEventHotKey(ref)
            raise RuntimeError(f'Ctrl+Cmd+Option+G недоступно: {status}')
        try:carbon.RunApplicationEventLoop()
        finally:
            carbon.UnregisterEventHotKey(ref);carbon.UnregisterEventHotKey(snapref)
    else:
        if os.environ.get('XDG_SESSION_TYPE')=='wayland':
            raise RuntimeError('Wayland: назначьте команду tthings --region в сочетаниях клавиш рабочего стола. KDE: --enable-hotkey.')
        from ctypes.util import find_library
        x=ctypes.CDLL(find_library('X11'))
        x.XOpenDisplay.argtypes=[ctypes.c_char_p];x.XOpenDisplay.restype=ctypes.c_void_p
        display=x.XOpenDisplay(None)
        if not display:raise RuntimeError('X11 display недоступен')
        x.XDefaultRootWindow.argtypes=[ctypes.c_void_p];x.XDefaultRootWindow.restype=ctypes.c_ulong
        x.XKeysymToKeycode.argtypes=[ctypes.c_void_p,ctypes.c_ulong];x.XKeysymToKeycode.restype=ctypes.c_uint
        x.XGrabKey.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_uint,ctypes.c_ulong,ctypes.c_int,ctypes.c_int,ctypes.c_int]
        x.XNextEvent.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        x.XCloseDisplay.argtypes=[ctypes.c_void_p]
        root=x.XDefaultRootWindow(display);key=x.XKeysymToKeycode(display,ord('g'))
        for ctrl in (0,4):
            for locks in (0,2,16,18):x.XGrabKey(display,key,8|64|ctrl|locks,root,False,1,1)
        class XKeyEvent(ctypes.Structure):
            _fields_=[('type',ctypes.c_int),('serial',ctypes.c_ulong),('send_event',ctypes.c_int),('display',ctypes.c_void_p),('window',ctypes.c_ulong),('root',ctypes.c_ulong),('subwindow',ctypes.c_ulong),('time',ctypes.c_ulong),('x',ctypes.c_int),('y',ctypes.c_int),('x_root',ctypes.c_int),('y_root',ctypes.c_int),('state',ctypes.c_uint),('keycode',ctypes.c_uint),('same_screen',ctypes.c_int)]
        event=(ctypes.c_long*24)()
        try:
            while True:
                x.XNextEvent(display,ctypes.byref(event))
                if ctypes.cast(ctypes.byref(event),ctypes.POINTER(ctypes.c_int))[0]==2:
                    pressed=ctypes.cast(ctypes.byref(event),ctypes.POINTER(XKeyEvent)).contents
                    spawn_window(True,snap=bool(pressed.state&4))
        finally:x.XCloseDisplay(display)
