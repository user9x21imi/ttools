"""User-prefix install/update transactions owned by ttools, never a background updater."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

APP_ID='tthings'


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,name=tempfile.mkstemp(prefix='.metadata-',dir=path.parent)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
        os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)


class PrefixLock:
    def __init__(self,prefix,shared=False):self.path=Path(prefix)/'.tthings/deploy.lock';self.shared=shared;self.file=None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True);self.file=self.path.open('a+b')
        try:
            if os.name=='posix':
                import fcntl
                fcntl.flock(self.file.fileno(),(fcntl.LOCK_SH if self.shared else fcntl.LOCK_EX)|fcntl.LOCK_NB)
            else:
                import msvcrt
                self.file.seek(0);self.file.write(b'0');self.file.flush();self.file.seek(0)
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
        except OSError as exc:
            self.file.close();self.file=None
            raise RuntimeError('tthings занят: работает экземпляр или другая операция установки/обновления. Сначала штатно остановите приложение.') from exc
        return self
    def __exit__(self,*args):
        if self.file:
            if os.name=='posix':
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_UN)
            else:
                import msvcrt
                self.file.seek(0);msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
            self.file.close();self.file=None


def read_metadata(prefix):
    try:return json.loads((Path(prefix)/'.tthings/install.json').read_text())
    except (OSError,ValueError):return None


def executable_path(prefix):return Path(prefix)/'bin'/('tthings.exe' if os.name=='nt' else 'tthings')


def process_identity(pid):
    if sys.platform.startswith('linux'):
        try:
            text=Path(f'/proc/{pid}/stat').read_text();fields=text[text.rfind(')')+2:].split()
            return None if fields[0]=='Z' else fields[19]
        except (OSError,IndexError):return None
    try:os.kill(pid,0);return str(pid)
    except (OSError,ProcessLookupError):return None


def active_instances(prefix):
    result=[]
    for path in (Path(prefix)/'.tthings/instances').glob('*.json'):
        try:
            record=json.loads(path.read_text());pid=int(record['pid'])
            if process_identity(pid)==record['identity']:result.append(record)
            else:path.unlink(missing_ok=True)
        except (OSError,ValueError,KeyError,TypeError):continue
    return result


class InstanceLease:
    def __init__(self,prefix=None):
        prefix=prefix or os.environ.get("TTOOLS_TTHINGS_PREFIX")
        self.prefix=Path(prefix) if prefix else None;self.lock=None;self.record=None
    def start(self):
        if self.prefix is None:
            candidate=Path(sys.executable if getattr(sys,'frozen',False) else sys.argv[0]).resolve()
            if candidate.parent.name!='bin':return
            self.prefix=candidate.parent.parent
        metadata=read_metadata(self.prefix)
        if not metadata or metadata.get('app_id')!=APP_ID:return
        self.lock=PrefixLock(self.prefix,shared=True);self.lock.__enter__()
        self.record=self.prefix/'.tthings/instances'/f'{os.getpid()}.json'
        try:atomic_json(self.record,{'pid':os.getpid(),'identity':process_identity(os.getpid()),'app_id':APP_ID})
        except Exception:self.lock.__exit__();self.lock=None;raise
    def close(self):
        if self.record:self.record.unlink(missing_ok=True)
        if self.lock:self.lock.__exit__();self.lock=None


def stop_managed(prefix,timeout=6):
    if not sys.platform.startswith('linux'):raise RuntimeError('Управляемая остановка проверена только на Linux; на других ОС ttools должен закрыть свой дочерний процесс.')
    instances=active_instances(prefix)
    for record in instances:
        if record['pid']==os.getpid():continue
        if process_identity(record['pid'])==record['identity']:
            try:os.kill(record['pid'],signal.SIGINT)
            except ProcessLookupError:pass
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        live=[r for r in active_instances(prefix) if r['pid']!=os.getpid()]
        if not live:return {'status':'stopped','count':len(instances)}
        time.sleep(.05)
    raise RuntimeError('Экземпляр не завершился штатно за отведённое время; обновление не применено. ttools должен дождаться своего Popen, без killall.')


def _version_tuple(text):
    try:return tuple(int(n) for n in text.split('.'))
    except (ValueError,AttributeError):return ()


def choose_artifact(manifest):
    machine=platform.machine().casefold();system=sys.platform
    key='linux-x86_64' if system.startswith('linux') and machine in ('x86_64','amd64') else 'windows-x86_64' if os.name=='nt' else 'macos-arm64' if system=='darwin' and machine in ('arm64','aarch64') else 'macos-x86_64' if system=='darwin' else None
    artifacts=manifest.get('artifacts',[])
    native=next((a for a in artifacts if a.get('platform')==key),None)
    if native and key and key.startswith('linux'):
        libc,version=platform.libc_ver()
        if libc!='glibc' or _version_tuple(version)<_version_tuple(native.get('minimum_glibc','0')):native=None
    if native:return native
    source=next((a for a in artifacts if a.get('platform')=='python-source'),None)
    if source and sys.version_info>=(3,10):return source
    raise RuntimeError('Нет совместимого артефакта; нужен соответствующий ОС runtime или Python >=3.10 для source fallback.')


def _download(url,path):
    if urllib.parse.urlparse(url).scheme!='https':raise RuntimeError('Удалённый канал обновлений должен использовать HTTPS')
    with urllib.request.urlopen(url,timeout=25) as response,path.open('wb') as output:shutil.copyfileobj(response,output)


def read_manifest(location):
    text=str(location)
    if text.startswith('https://'):
        with urllib.request.urlopen(text,timeout=25) as response:data=response.read(2*1024*1024+1)
        if len(data)>2*1024*1024:raise RuntimeError('Манифест слишком большой')
        manifest=json.loads(data);base=text
    else:
        path=Path(location).expanduser().resolve();manifest=json.loads(path.read_text());base=path.parent
    if manifest.get('schema_version')!=1 or manifest.get('app_id')!=APP_ID or not manifest.get('version'):raise RuntimeError('Неверный манифест tthings')
    return manifest,base


def run_argv(path,kind):
    if kind=='zipapp':
        python=shutil.which('python3') or shutil.which('python') or (sys.executable if not getattr(sys,'frozen',False) else None)
        if not python:raise RuntimeError('Source fallback требует Python >=3.10')
        return [python,str(path)]
    return [str(path)]


def probe(path,kind,version):
    args=run_argv(path,kind)
    # Children emit UTF-8; never let the host locale (e.g. Windows cp1251/cp866)
    # decode them, and never let a decode error mask a real failure.
    result=subprocess.run(args+['--version'],capture_output=True,text=True,check=True,timeout=15,
                          encoding='utf-8',errors='replace',env=_utf8_env())
    if result.stdout.strip()!=version:raise RuntimeError(f'Версия бинарника {result.stdout.strip()!r} не совпадает с манифестом {version!r}')
    catalog=json.loads(subprocess.check_output(args+['--list','--json'],text=True,timeout=15,
                                               encoding='utf-8',errors='replace',env=_utf8_env()))
    if not isinstance(catalog,list) or not catalog:raise RuntimeError('Артефакт не вернул каталог')
    return catalog


def _copy_atomic(source,target):
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    descriptor,name=tempfile.mkstemp(prefix='.tthings-',dir=target.parent);os.close(descriptor)
    try:shutil.copy2(source,name);os.replace(name,target)
    finally:Path(name).unlink(missing_ok=True)


def apply_update(location,prefix,forced_platform=None):
    prefix=Path(prefix).expanduser().resolve();manifest,base=read_manifest(location)
    artifact=choose_artifact(manifest) if forced_platform is None else next(a for a in manifest['artifacts'] if a['platform']==forced_platform)
    kind=artifact.get('kind','executable');sha=artifact.get('sha256','')
    if len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha.lower()):raise RuntimeError('В манифесте нет корректного SHA-256')
    with PrefixLock(prefix):
        if active_instances(prefix):raise RuntimeError('Сначала остановите управляемые экземпляры tthings')
        state=prefix/'.tthings';target=executable_path(prefix);metadata_path=state/'install.json';backup=state/'previous.bin';backup_meta=state/'previous.json'
        oldmeta=read_metadata(prefix)
        if target.exists() and digest(target)==sha and oldmeta and oldmeta.get('version')==manifest['version']:
            return {'status':'unchanged','version':manifest['version'],'path':str(target),'kind':kind}
        with tempfile.TemporaryDirectory(prefix='stage-',dir=state) as td:
            stage=Path(td)/'tthings'
            if artifact.get('url'):
                url=artifact['url']
                if not str(url).startswith('https://') and isinstance(base,str):url=urllib.parse.urljoin(base,url)
                _download(url,stage)
            else:
                if not isinstance(base,Path):raise RuntimeError('HTTPS-манифест требует URL артефакта')
                relative=artifact.get('path')
                if not relative:raise RuntimeError('Нет URL или локального пути артефакта')
                source=(base/relative).resolve()
                try:source.relative_to(base)
                except ValueError:raise RuntimeError('Путь артефакта выходит за пределы пакета')
                shutil.copy2(source,stage)
            if digest(stage)!=sha:raise RuntimeError('SHA-256 не совпадает: текущая установка не изменена')
            if os.name!='nt':stage.chmod(0o755)
            catalog=probe(stage,kind,manifest['version'])
            had_previous=target.exists()
            if had_previous:
                _copy_atomic(target,backup)
                atomic_json(backup_meta,oldmeta or {'app_id':APP_ID,'version':'unknown','kind':'executable'})
            try:
                _copy_atomic(stage,target)
                probe(target,kind,manifest['version'])
                metadata={'app_id':APP_ID,'version':manifest['version'],'sha256':sha,'kind':kind,'platform':artifact['platform'],'updated_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'effect_count':sum(e.get('kind')=='effect' for e in catalog),'tool_count':sum(e.get('kind')=='tool' for e in catalog),'update_owner':'ttools'}
                atomic_json(metadata_path,metadata)
            except Exception:
                if had_previous:_copy_atomic(backup,target)
                else:target.unlink(missing_ok=True)
                if oldmeta:atomic_json(metadata_path,oldmeta)
                else:metadata_path.unlink(missing_ok=True)
                raise
        return {'status':'installed' if not had_previous else 'updated',**metadata,'path':str(target)}


def rollback(prefix):
    prefix=Path(prefix).expanduser().resolve()
    with PrefixLock(prefix):
        state=prefix/'.tthings';backup=state/'previous.bin'
        if not backup.exists():raise RuntimeError('Нет предыдущей версии для отката')
        meta=json.loads((state/'previous.json').read_text())
        if meta.get('version')=='unknown':raise RuntimeError('У предыдущей версии нет проверяемой метаинформации')
        probe(backup,meta.get('kind','executable'),meta['version'])
        _copy_atomic(backup,executable_path(prefix));atomic_json(state/'install.json',meta)
        return {'status':'rolled_back','version':meta['version'],'path':str(executable_path(prefix))}


def install_current(prefix):
    """Install an already prepared runtime/source zipapp without desktop side effects."""
    from . import __version__
    with tempfile.TemporaryDirectory(prefix='tthings-install-') as td:
        base=Path(td);payload=base/'tthings'
        if getattr(sys,'frozen',False):shutil.copy2(sys.executable,payload);kind='executable';plat='linux-x86_64' if sys.platform.startswith('linux') else 'windows-x86_64' if os.name=='nt' else 'macos-'+platform.machine()
        else:
            import zipapp
            package=base/'app';package.mkdir()
            shutil.copytree(Path(__file__).parent,package/'tthings',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            zipapp.create_archive(package,payload,interpreter='/usr/bin/env python3',main='tthings.__main__:main',compressed=True);kind='zipapp';plat='python-source'
        if os.name!='nt':payload.chmod(0o755)
        manifest={'schema_version':1,'app_id':APP_ID,'version':__version__,'requires_stop':True,'artifacts':[{'platform':plat,'kind':kind,'url':None,'path':'tthings','sha256':digest(payload)}]}
        atomic_json(base/'update.json',manifest)
        return apply_update(base/'update.json',prefix)


def _utf8_env():
    env=dict(os.environ);env['PYTHONUTF8']='1';env['PYTHONIOENCODING']='utf-8'
    return env
