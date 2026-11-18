"""Autonomous platform detection and system facts. No external commands."""
import ctypes as C
import importlib.resources
import json
import os
from pathlib import Path
import platform
import re
import sys
import time
from .metrics import read_text,disk_space,parse_mem,battery


def os_release():
    for path in ('/etc/os-release','/usr/lib/os-release'):
        text=read_text(path)
        if text:
            result={}
            for line in text.splitlines():
                key,sep,value=line.partition('=')
                if sep:result[key]=value.strip().strip('"\'')
            return result
    return {}


def normalized(name):return re.sub(r'[^\w]','',name.casefold()).replace('_','')


def logo_catalog():
    resource=importlib.resources.files('tthings').joinpath('assets/logos.json')
    return json.loads(resource.read_text(encoding='utf-8'))['logos']


def choose_logo(catalog,system=None,release=None):
    system=system or platform.system();release=os_release() if release is None and system=='Linux' else (release or {})
    aliases={}
    for key,value in catalog.items():
        if key.casefold().endswith('_small'):continue
        for name in [key,*value.get('names',[])]:aliases.setdefault(normalized(name),key)
    if system=='Windows':
        build=sys.getwindowsversion().build if hasattr(sys,'getwindowsversion') else 0
        candidates=['Windows 11','Windows'] if build>=22000 else ['Windows 10','Windows'] if build else ['Windows']
    elif system=='Darwin':candidates=['macOS','Mac']
    elif system=='Linux':candidates=[release.get('ID',''),release.get('NAME',''),*release.get('ID_LIKE','').split(),'Linux']
    else:candidates=[system]
    for name in candidates:
        key=aliases.get(normalized(name))
        if key:return key,catalog[key]
    # There is no SteamOS fallback. A generic OS mark is used if a new OS is unknown.
    return 'Generic',{'lines':'  $1OS\n  ██\n ████','names':['Generic'],'colors':['36']}


def sysctl_bytes(name):
    try:
        lib=C.CDLL('/usr/lib/libSystem.B.dylib');f=lib.sysctlbyname
        f.argtypes=[C.c_char_p,C.c_void_p,C.POINTER(C.c_size_t),C.c_void_p,C.c_size_t];f.restype=C.c_int
        size=C.c_size_t()
        if f(name.encode(),None,C.byref(size),None,0):return b''
        buffer=C.create_string_buffer(size.value)
        if f(name.encode(),buffer,C.byref(size),None,0):return b''
        return buffer.raw[:size.value]
    except (OSError,AttributeError):return b''


def sysctl_text(name):return sysctl_bytes(name).rstrip(b'\x00').decode('utf-8','replace')


def windows_facts():
    result={}
    try:
        import winreg as W
        with W.OpenKey(W.HKEY_LOCAL_MACHINE,r'SOFTWARE\Microsoft\Windows NT\CurrentVersion') as key:
            for field in ('ProductName','DisplayVersion','CurrentBuildNumber'):
                try:result[field]=str(W.QueryValueEx(key,field)[0])
                except OSError:pass
        with W.OpenKey(W.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:result['cpu']=W.QueryValueEx(key,'ProcessorNameString')[0].strip()
        with W.OpenKey(W.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\BIOS') as key:
            result['model']=' '.join(str(W.QueryValueEx(key,name)[0]) for name in ('SystemManufacturer','SystemProductName'))
    except OSError:pass
    try:
        tick=C.windll.kernel32.GetTickCount64;tick.restype=C.c_ulonglong;result['uptime']=tick()/1000
    except (AttributeError,OSError):pass
    return result


def native_facts(system,release):
    result={}
    if system=='Linux':
        result['os']=release.get('PRETTY_NAME') or release.get('NAME') or 'Linux'
        for line in read_text('/proc/cpuinfo').splitlines():
            if line.startswith(('model name','Hardware')):result['cpu']=line.partition(':')[2].strip();break
        result['model']=' '.join(read_text('/sys/devices/virtual/dmi/id/'+name).strip() for name in ('sys_vendor','product_name')).strip()
        memory=parse_mem(read_text('/proc/meminfo'));result['memory']=(memory['used'],memory['total'])
        try:result['uptime']=float(read_text('/proc/uptime').split()[0])
        except (IndexError,ValueError):pass
        result['battery']=battery()
    elif system=='Windows':
        facts=windows_facts();name=facts.get('ProductName','Windows')
        try:
            if int(facts.get('CurrentBuildNumber','0'))>=22000:name=name.replace('Windows 10','Windows 11')
        except ValueError:pass
        result.update(os=(name+' '+facts.get('DisplayVersion','')).strip(),cpu=facts.get('cpu'),model=facts.get('model'),uptime=facts.get('uptime'))
    elif system=='Darwin':
        result.update(os='macOS '+sysctl_text('kern.osproductversion'),cpu=sysctl_text('machdep.cpu.brand_string'),model=sysctl_text('hw.model'))
        boot=sysctl_bytes('kern.boottime')
        if len(boot)>=8:result['uptime']=max(0,time.time()-int.from_bytes(boot[:8],sys.byteorder,signed=True))
    else:result['os']=system
    if system!='Linux':
        # psutil is included in matching application builds, not a system program.
        try:
            import psutil
            memory=psutil.virtual_memory();result['memory']=(memory.total-memory.available,memory.total)
            bat=psutil.sensors_battery() if hasattr(psutil,'sensors_battery') else None
            if bat:result['battery']=[{'name':'Battery','percent':bat.percent,'status':'Charging' if bat.power_plugged else 'Discharging'}]
        except (ImportError,OSError):pass
    return result


def compact_disks():
    mounts=[]
    for line in read_text('/proc/self/mountinfo').splitlines():
        left,sep,right=line.partition(' - ');parts=left.split();tail=right.split()
        if sep and len(parts)>=5 and len(tail)>=2:
            from .metrics import unescape_mount
            mounts.append((unescape_mount(parts[4]),unescape_mount(tail[1])))
    result=[];seen=set()
    for row in disk_space():
        path=row['path'];matching=[(mount,device) for mount,device in mounts if path==mount or path.startswith(mount.rstrip('/')+'/')]
        source=max(matching,key=lambda pair:len(pair[0]))[1] if matching else path
        if not source.startswith('/dev/'):
            try:source='dev:'+str(os.stat(path).st_dev)
            except OSError:pass
        if source in seen:continue
        seen.add(source);result.append(row)
    return result


def gather_system_data(catalog=None,system=None,release=None):
    system=system or platform.system();release=os_release() if release is None and system=='Linux' else (release or {})
    catalog=logo_catalog() if catalog is None else catalog;key,logo=choose_logo(catalog,system,release)
    from .system_fetch import parse_logo
    facts=native_facts(system,release);rows=[]
    def add(label,value):
        if value not in (None,''):rows.append((label,str(value)))
    add('OS',facts.get('os',system));add('Model',facts.get('model'));add('Kernel',platform.release());add('Arch',platform.machine())
    uptime=facts.get('uptime')
    if uptime is not None:add('Uptime',f'{int(uptime)//3600}h {int(uptime)%3600//60}m')
    add('Desktop',os.environ.get('XDG_CURRENT_DESKTOP'));add('Session',os.environ.get('XDG_SESSION_TYPE'));add('CPU',facts.get('cpu'));add('Threads',os.cpu_count())
    if facts.get('memory'):
        used,total=facts['memory'];add('Memory',f'{used/1024**3:.1f} / {total/1024**3:.1f} GiB')
    for disk in compact_disks()[:6]:add('Disk '+disk['path'],f"{disk['used']/1024**3:.1f} / {disk['total']/1024**3:.1f} GiB")
    for bat in facts.get('battery',[]):add('Battery',str(bat['percent'])+'% · '+bat['status'])
    return {'os':facts.get('os',system),'rows':rows,'logo':parse_logo(logo),'logo_name':key,'backend':'native','logo_count':len(catalog)}
