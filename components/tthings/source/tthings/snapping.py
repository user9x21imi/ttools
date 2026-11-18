"""Window geometry and proximity snapping; never moves existing windows."""
import ctypes as C
from ctypes.util import find_library
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid


def normalize_rectangles(values):
    result=[]
    for value in values:
        try:
            rect=[float(n) for n in value]
            if len(rect)!=4 or not all(math.isfinite(n) for n in rect):continue
            if rect[2]<1 or rect[3]<1:continue
            result.append(rect)
        except (ValueError,TypeError):continue
    return result


def snap_point(x,y,rectangles,threshold=14):
    # Edge segments, not infinite guidelines: unrelated distant windows don't attract.
    bestx,besty=threshold+1,threshold+1
    sx,sy=x,y
    for left,top,width,height in rectangles:
        if top-threshold<=y<=top+height+threshold:
            for edge in (left,left+width):
                distance=abs(x-edge)
                if distance<=threshold and distance<bestx:sx,bestx=edge,distance
        if left-threshold<=x<=left+width+threshold:
            for edge in (top,top+height):
                distance=abs(y-edge)
                if distance<=threshold and distance<besty:sy,besty=edge,distance
    return sx,sy


def _kwin_rectangles():
    """Short-lived D-Bus receiver. KWin sends geometry; no titles or screenshots."""
    command=shutil.which('qdbus6') or shutil.which('qdbus')
    if not command:raise RuntimeError('Не найден qdbus для получения границ окон KDE')
    libraries=[find_library(name) for name in ('gio-2.0','glib-2.0','gobject-2.0')]
    if not all(libraries):raise RuntimeError('Не найдены системные библиотеки GLib/GIO для KDE')
    gio,glib,gobject=(C.CDLL(name) for name in libraries)
    def bind(lib,name,restype,*args):
        f=getattr(lib,name);f.restype=restype;f.argtypes=list(args);return f
    ptr=C.c_void_p;str_=C.c_char_p
    bus_get=bind(gio,'g_bus_get_sync',ptr,C.c_int,ptr,ptr)
    unique_name=bind(gio,'g_dbus_connection_get_unique_name',str_,ptr)
    node_new=bind(gio,'g_dbus_node_info_new_for_xml',ptr,str_,ptr)
    lookup=bind(gio,'g_dbus_node_info_lookup_interface',ptr,ptr,str_)
    variant_child=bind(glib,'g_variant_get_child_value',ptr,ptr,C.c_size_t)
    variant_string=bind(glib,'g_variant_get_string',str_,ptr,ptr)
    variant_unref=bind(glib,'g_variant_unref',None,ptr)
    return_value=bind(gio,'g_dbus_method_invocation_return_value',None,ptr,ptr)
    iterate=bind(glib,'g_main_context_iteration',C.c_int,ptr,C.c_int)
    unregister=bind(gio,'g_dbus_connection_unregister_object',C.c_int,ptr,C.c_uint)
    node_unref=bind(gio,'g_dbus_node_info_unref',None,ptr)
    unref=bind(gobject,'g_object_unref',None,ptr)
    callback_type=C.CFUNCTYPE(None,ptr,str_,str_,str_,str_,ptr,ptr,ptr)
    class VTable(C.Structure):
        _fields_=[('method',callback_type),('get',ptr),('set',ptr),('padding',ptr*8)]
    register=bind(gio,'g_dbus_connection_register_object',C.c_uint,ptr,str_,ptr,C.POINTER(VTable),ptr,ptr,ptr)
    bus=bus_get(2,None,None) # G_BUS_TYPE_SESSION
    if not bus:raise RuntimeError('Нет доступа к D-Bus сеанса KDE')
    node=None;registration=0;script_id=None;data=[];received=[]
    try:
        node=node_new(b'<node><interface name="app.tthings.Snap"><method name="Deliver"><arg type="s" direction="in"/></method></interface></node>',None)
        def deliver(connection,sender,path,interface,method,parameters,invocation,user_data):
            child=None
            try:
                child=variant_child(parameters,0)
                value=json.loads(variant_string(child,None).decode())
                if isinstance(value,list):data.extend(normalize_rectangles(value));received.append(True)
            except (ValueError,TypeError,UnicodeError):pass
            finally:
                if child:variant_unref(child)
                return_value(invocation,None)
        callback=callback_type(deliver);table=VTable(callback,None,None,(ptr*8)())
        registration=register(bus,b'/app/tthings/Snap',lookup(node,b'app.tthings.Snap'),C.byref(table),None,None,None)
        if not registration:raise RuntimeError('Не удалось зарегистрировать приёмник границ окон')
        destination=unique_name(bus).decode();name='tthings-snap-'+uuid.uuid4().hex
        script='''var rects=[];
workspace.windowList().forEach(function(w) {
    if (w.minimized || w.desktopWindow || w.dock || (!w.normalWindow && !w.dialog && !w.utility)) return;
    if (w.desktops && w.desktops.length && w.desktops.indexOf(workspace.currentDesktop)<0) return;
    if (w.activities && w.activities.length && w.activities.indexOf(workspace.currentActivity)<0) return;
    var g=w.frameGeometry;
    if(g.width>0 && g.height>0) rects.push([g.x,g.y,g.width,g.height]);
});
callDBus(DESTINATION,"/app/tthings/Snap","app.tthings.Snap","Deliver",JSON.stringify(rects));
'''.replace('DESTINATION',json.dumps(destination))
        with tempfile.TemporaryDirectory(prefix='tthings-kwin-') as directory:
            path=Path(directory)/'geometry.js';path.write_text(script)
            loaded=subprocess.run([command,'org.kde.KWin','/Scripting','org.kde.kwin.Scripting.loadScript',str(path),name],capture_output=True,text=True,timeout=2,check=True)
            script_id=int(loaded.stdout.strip())
            if script_id<0:raise RuntimeError('KWin отклонил скрипт границ окон')
            process=subprocess.Popen([command,'org.kde.KWin',f'/Scripting/Script{script_id}','org.kde.kwin.Script.run'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            deadline=time.monotonic()+2
            try:
                while not received and time.monotonic()<deadline:
                    while iterate(None,False):pass
                    time.sleep(.005)
                if not received:raise RuntimeError('KWin не передал границы окон')
            finally:
                if process.poll() is None:process.terminate()
                process.wait(timeout=1)
            # unloadScript takes the script's plugin name, not its integer ID.
            subprocess.run([command,'org.kde.KWin','/Scripting','org.kde.kwin.Scripting.unloadScript',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=1)
            script_id=None
        return data
    finally:
        if script_id is not None:
            try:subprocess.run([command,'org.kde.KWin','/Scripting','org.kde.kwin.Scripting.unloadScript',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=1)
            except (OSError,subprocess.SubprocessError):pass
        if registration:unregister(bus,registration)
        if node:node_unref(node)
        unref(bus)


def _windows_rectangles():
    from ctypes import wintypes as W
    user=C.windll.user32;rects=[]
    callback_type=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    user.IsWindowVisible.argtypes=[W.HWND];user.IsIconic.argtypes=[W.HWND]
    user.GetWindowRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
    try:dwm=C.windll.dwmapi
    except OSError:dwm=None
    if dwm:dwm.DwmGetWindowAttribute.argtypes=[W.HWND,W.DWORD,C.c_void_p,W.DWORD]
    def collect(hwnd,param):
        if not user.IsWindowVisible(hwnd) or user.IsIconic(hwnd):return True
        rect=W.RECT()
        if dwm:
            cloaked=W.DWORD()
            if dwm.DwmGetWindowAttribute(hwnd,14,C.byref(cloaked),C.sizeof(cloaked))==0 and cloaked.value:return True
            found=dwm.DwmGetWindowAttribute(hwnd,9,C.byref(rect),C.sizeof(rect))==0
        else:found=False
        if not found and not user.GetWindowRect(hwnd,C.byref(rect)):return True
        rects.append([rect.left,rect.top,rect.right-rect.left,rect.bottom-rect.top]);return True
    callback=callback_type(collect)
    user.EnumWindows.argtypes=[callback_type,W.LPARAM];user.EnumWindows(callback,0)
    return normalize_rectangles(rects)


def own_window_rectangles():
    if os.name=='nt':return []
    directory=Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'tthings/windows'
    result=[]
    for path in directory.glob('*.json'):
        try:
            value=json.loads(path.read_text())
            os.kill(int(value['pid']),0)
            if time.time()-value['updated']<10:result.extend(normalize_rectangles([value['rect']]))
        except (OSError,ValueError,KeyError,TypeError):pass
    return result


def window_rectangles():
    try:
        if os.name=='nt':return _windows_rectangles()
        if sys.platform=='darwin':
            script="ObjC.import('CoreGraphics');var a=ObjC.deepUnwrap($.CGWindowListCopyWindowInfo(1,0));JSON.stringify(a.filter(w=>w.kCGWindowLayer===0&&w.kCGWindowAlpha>0).map(w=>[w.kCGWindowBounds.X,w.kCGWindowBounds.Y,w.kCGWindowBounds.Width,w.kCGWindowBounds.Height]));"
            p=subprocess.run(['osascript','-l','JavaScript','-e',script],capture_output=True,text=True,check=True,timeout=3)
            return normalize_rectangles(json.loads(p.stdout))
        if 'KDE' in os.environ.get('XDG_CURRENT_DESKTOP',''):return _kwin_rectangles()+own_window_rectangles()
        if os.environ.get('XDG_SESSION_TYPE')!='wayland' and shutil.which('wmctrl'):
            p=subprocess.run(['wmctrl','-lG'],capture_output=True,text=True,check=True,timeout=2)
            values=[]
            for line in p.stdout.splitlines():
                fields=line.split()
                if len(fields)>=6:values.append(fields[2:6])
            return normalize_rectangles(values)
        raise RuntimeError('Привязка к чужим окнам на этом рабочем столе пока не поддержана')
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        raise RuntimeError(f'Не удалось получить рамки окон: {exc}') from exc
