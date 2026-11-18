"""Read-only system counters. Linux needs no third-party Python modules."""
from pathlib import Path
import datetime as dt
import os
import platform
import re
import shutil
import sys
import time


def read_text(path):
    try:return Path(path).read_text(errors='replace')
    except OSError:return ''


def parse_cpu(text):
    result={}
    for line in text.splitlines():
        parts=line.split()
        if not parts or not re.fullmatch(r'cpu\d*',parts[0]):continue
        values=[int(n) for n in parts[1:9]] # guest fields are already in user/nice
        if len(values)>=4:result[parts[0]]=(sum(values),values[3]+(values[4] if len(values)>4 else 0))
    return result


def parse_mem(text):
    values={}
    for line in text.splitlines():
        fields=line.replace(':','').split()
        if len(fields)>=2:
            try:values[fields[0]]=int(fields[1])*1024
            except ValueError:pass
    total=values.get('MemTotal',0)
    available=values.get('MemAvailable',sum(values.get(k,0) for k in ['MemFree','Buffers','Cached']))
    swap=values.get('SwapTotal',0)
    return {'total':total,'available':available,'used':max(0,total-available),'percent':100*(total-available)/total if total else None,
            'swap_total':swap,'swap_used':max(0,swap-values.get('SwapFree',0))}


def parse_net(text):
    result={}
    for line in text.splitlines():
        if ':' not in line:continue
        name,fields=line.rsplit(':',1);values=fields.split()
        if len(values)<16:continue
        result[name.strip()]={key:int(values[i]) for key,i in [('rx_bytes',0),('rx_packets',1),('rx_errors',2),('rx_drops',3),('tx_bytes',8),('tx_packets',9),('tx_errors',10),('tx_drops',11)]}
    return result


def parse_disks(text,devices=None):
    result={}
    for line in text.splitlines():
        p=line.split()
        if len(p)<14 or (devices is not None and p[2] not in devices):continue
        if p[2].startswith(('loop','ram','zram')):continue
        result[p[2]]={'read_bytes':int(p[5])*512,'write_bytes':int(p[9])*512,'reads':int(p[3]),'writes':int(p[7]),'busy_ms':int(p[12]),'in_flight':int(p[11])}
    return result


def delta_rates(current,previous,elapsed,keys):
    if previous is None or elapsed<=0:return {k:None for k in keys}
    return {key:(current[key]-previous[key])/elapsed if key in previous and current[key]>=previous[key] else None for key in keys}


def unescape_mount(value):
    return re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),value)


def disk_space():
    mounts=[]
    if sys.platform.startswith('linux'):
        for line in read_text('/proc/self/mountinfo').splitlines():
            left,sep,right=line.partition(' - ')
            if not sep:continue
            fields=left.split();kind=right.split()[0]
            if len(fields)<5:continue
            path=unescape_mount(fields[4])
            if path.startswith(('/proc','/sys','/dev')) or kind in ('tmpfs','devtmpfs','cgroup2','squashfs','tracefs','debugfs'):continue
            mounts.append((path,kind))
    elif os.name=='nt':
        import ctypes
        mask=ctypes.windll.kernel32.GetLogicalDrives()
        mounts=[(chr(65+i)+':\\','') for i in range(26) if mask&(1<<i)]
    else:
        mounts=[('/','')]+[(str(p),'') for p in Path('/Volumes').glob('*') if p.is_dir()]
    if not mounts:mounts=[(str(Path.home()),'')]
    seen=set();result=[]
    # HOME first gives a useful capacity row even when bind-mounts share the device.
    mounts=[(str(Path.home()),'home')]+mounts
    for path,kind in mounts:
        try:
            stat=os.stat(path);key=stat.st_dev if os.name!='nt' else path[:2]
            if key in seen:continue
            usage=shutil.disk_usage(path)
            if usage.total<=0:continue
            seen.add(key)
            result.append({'path':path,'type':kind,'total':usage.total,'used':usage.used,'free':usage.free,'percent':usage.used/usage.total*100})
        except OSError:continue
    return result


def battery():
    result=[]
    if sys.platform.startswith('linux'):
        for path in Path('/sys/class/power_supply').glob('*'):
            if read_text(path/'type').strip()!='Battery':continue
            try:percent=float(read_text(path/'capacity').strip())
            except ValueError:percent=None
            result.append({'name':path.name,'percent':percent,'status':read_text(path/'status').strip() or 'unknown'})
    return result


def temperatures():
    result=[]
    for path in Path('/sys/class/thermal').glob('thermal_zone*'):
        try:value=float(read_text(path/'temp'))/1000
        except ValueError:continue
        if -20<value<150:result.append({'name':read_text(path/'type').strip() or path.name,'celsius':value})
    for path in Path('/sys/class/hwmon').glob('hwmon*'):
        name=read_text(path/'name').strip()
        for sensor in path.glob('temp*_input'):
            try:value=float(read_text(sensor))/1000
            except ValueError:continue
            if -20<value<150:result.append({'name':name+' '+(read_text(sensor.with_name(sensor.name.replace('_input','_label'))).strip() or sensor.stem),'celsius':value})
    return result


def gpu_status():
    result=[]
    for device in Path('/sys/class/drm').glob('card*/device'):
        busy=read_text(device/'gpu_busy_percent').strip()
        used=read_text(device/'mem_info_vram_used').strip();total=read_text(device/'mem_info_vram_total').strip()
        if not busy and not total:continue
        try:result.append({'name':device.parent.name,'percent':float(busy) if busy else None,'memory_used':int(used) if used else None,'memory_total':int(total) if total else None})
        except ValueError:continue
    return result


class Sampler:
    def __init__(self):self.previous=None;self.when=None;self.previous_processes={};self.capacity=[];self.capacity_at=-99

    def linux_raw(self,with_processes=False):
        cpu=parse_cpu(read_text('/proc/stat'))
        if not cpu:raise RuntimeError('Не удалось прочитать счётчики CPU /proc/stat')
        devices={p.name for p in Path('/sys/block').glob('*')}
        networks=parse_net(read_text('/proc/net/dev'))
        for name,value in networks.items():value['state']=read_text(Path('/sys/class/net')/name/'operstate').strip() or 'unknown'
        data={'cpu':cpu,'memory':parse_mem(read_text('/proc/meminfo')),'network':networks,'disks':parse_disks(read_text('/proc/diskstats'),devices),'battery':battery(),'temperatures':temperatures(),'gpu':gpu_status()}
        try:data['uptime']=float(read_text('/proc/uptime').split()[0])
        except (ValueError,IndexError):data['uptime']=None
        data['load']=list(os.getloadavg()) if hasattr(os,'getloadavg') else []
        data['processes']=self.linux_processes() if with_processes else []
        return data

    def linux_processes(self):
        result=[];ticks=os.sysconf('SC_CLK_TCK');pages=os.sysconf('SC_PAGE_SIZE')
        for path in Path('/proc').glob('[0-9]*'):
            line=read_text(path/'stat');end=line.rfind(')')
            if end<0:continue
            fields=line[end+2:].split()
            try:
                result.append({'pid':int(path.name),'name':line[line.find('(')+1:end],
                               'cpu_seconds':(int(fields[11])+int(fields[12]))/ticks,'rss':max(0,int(fields[21]))*pages,'state':fields[0],'started':fields[19]})
            except (ValueError,IndexError):continue
        return result

    def portable_raw(self,with_processes=False):
        try:import psutil as ps
        except ImportError as exc:raise RuntimeError('Мониторинг этой ОС требует psutil; готовая сборка должна включать его. Для исходников: python -m pip install psutil.') from exc
        times=ps.cpu_times(percpu=True)
        cpu={}
        for i,c in enumerate(times):
            values=c._asdict();total=sum(v for k,v in values.items() if k not in ('guest','guest_nice'));idle=values.get('idle',0)+values.get('iowait',0)
            cpu['cpu'+str(i)]=(total,idle)
        cpu['cpu']=(sum(v[0] for v in cpu.values()),sum(v[1] for v in cpu.values()))
        vm=ps.virtual_memory();sw=ps.swap_memory();stats=ps.net_if_stats()
        net={k:{'rx_bytes':v.bytes_recv,'tx_bytes':v.bytes_sent,'rx_packets':v.packets_recv,'tx_packets':v.packets_sent,'rx_errors':v.errin,'tx_errors':v.errout,'rx_drops':v.dropin,'tx_drops':v.dropout,'state':'up' if k in stats and stats[k].isup else 'down'} for k,v in ps.net_io_counters(pernic=True,nowrap=False).items()}
        disks={k:{'read_bytes':v.read_bytes,'write_bytes':v.write_bytes,'reads':v.read_count,'writes':v.write_count,'busy_ms':getattr(v,'busy_time',None),'in_flight':None} for k,v in (ps.disk_io_counters(perdisk=True,nowrap=False) or {}).items()}
        bat=ps.sensors_battery() if hasattr(ps,'sensors_battery') else None
        processes=[]
        if with_processes:
            for proc in ps.process_iter(['pid','name','cpu_times','memory_info','status','create_time']):
                try:
                    info=proc.info;c=info['cpu_times'];mem=info['memory_info']
                    if c and mem:processes.append({'pid':info['pid'],'name':info['name'] or '?','cpu_seconds':c.user+c.system,'rss':mem.rss,'state':info['status'],'started':str(info['create_time'])})
                except (ps.Error,TypeError):continue
        return {'cpu':cpu,'memory':{'total':vm.total,'available':vm.available,'used':vm.total-vm.available,'percent':vm.percent,'swap_total':sw.total,'swap_used':sw.used},'network':net,'disks':disks,'battery':[{'name':'Battery','percent':bat.percent,'status':'charging' if bat.power_plugged else 'discharging'}] if bat else [],'temperatures':[],'gpu':[],'uptime':time.time()-ps.boot_time(),'load':list(os.getloadavg()) if hasattr(os,'getloadavg') else [],'processes':processes}

    def sample(self,with_processes=False,now=None):
        now=time.monotonic() if now is None else now
        raw=self.linux_raw(with_processes) if sys.platform.startswith('linux') else self.portable_raw(with_processes)
        elapsed=now-self.when if self.when is not None else 0
        previous=self.previous or {};cpus={}
        for name,(total,idle) in raw['cpu'].items():
            old=previous.get('cpu',{}).get(name)
            delta=total-old[0] if old else 0;di=idle-old[1] if old else 0
            cpus[name]=max(0,min(100,100*(delta-di)/delta)) if delta>0 and di>=0 else None
        for group,keys in [('network',['rx_bytes','tx_bytes']),('disks',['read_bytes','write_bytes','reads','writes'])]:
            for name,value in raw[group].items():
                old=previous.get(group,{}).get(name)
                value['rates']=delta_rates(value,old,elapsed,keys)
                if group=='disks':
                    busy=value['busy_ms'];oldbusy=old.get('busy_ms') if old else None
                    value['busy_percent']=min(100,(busy-oldbusy)/elapsed/10) if busy is not None and oldbusy is not None and busy>=oldbusy and elapsed>0 else None
        procs={}
        for proc in raw['processes']:
            key=(proc['pid'],proc['started']);old=self.previous_processes.get(key)
            proc['cpu_percent']=max(0,100*(proc['cpu_seconds']-old)/elapsed) if old is not None and elapsed>0 else None
            procs[key]=proc['cpu_seconds']
        self.previous_processes=procs
        if now-self.capacity_at>=10:self.capacity=disk_space();self.capacity_at=now
        self.previous=raw;self.when=now
        return {'timestamp':dt.datetime.now(dt.timezone.utc).isoformat(),'elapsed':elapsed,'cpu':cpus,'memory':raw['memory'],'network':raw['network'],'disks':raw['disks'],'mounts':self.capacity,'battery':raw['battery'],'temperatures':raw['temperatures'],'gpu':raw['gpu'],'uptime':raw['uptime'],'load':raw['load'],'processes':raw['processes'],'backend':'procfs' if sys.platform.startswith('linux') else 'psutil'}
