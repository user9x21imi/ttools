"""Verified downloads, cross-platform locking and atomic installation metadata."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import tempfile
import urllib.parse
import urllib.request
import zipfile

REPOSITORY = 'user9x21imi/ttools'
MAX_ARCHIVE = 700 * 1024 * 1024

def platform_id(system=None, machine=None):
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    arch = {'amd64':'x86_64','x86_64':'x86_64','aarch64':'arm64','arm64':'arm64'}.get(machine)
    family = {'Linux':'linux','Darwin':'macos','Windows':'windows'}.get(system)
    if not family or not arch:
        raise ValueError(f'Unsupported platform: {system}/{machine}')
    return f'{family}-{arch}'

def version_key(value):
    match=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc|preview)\.(\d+))?',value or '')
    if not match:raise ValueError('Invalid suite semantic version')
    major,minor,patch,stage,number=match.groups()
    return (int(major),int(minor),int(patch),1 if stage is None else 0,
            {'alpha':0,'preview':0,'beta':1,'rc':2,None:0}[stage],int(number or 0))


def default_prefix():
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'ttools'
    if platform.system() == 'Darwin':
        return Path.home()/'Library/Application Support/ttools'
    return Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'ttools-suite'

def prefix_path(value=None):
    return Path(value or os.environ.get('TTOOLS_PREFIX') or default_prefix()).expanduser().resolve()

def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.metadata-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as out:
            json.dump(value,out,ensure_ascii=False,indent=2)
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        os.replace(name,path)
    finally:
        Path(name).unlink(missing_ok=True)

def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024),b''):
            hasher.update(chunk)
    return hasher.hexdigest()

@contextmanager
def locked(prefix):
    prefix.mkdir(parents=True,exist_ok=True)
    with (prefix/'suite.lock').open('a+b') as stream:
        try:
            if os.name == 'nt':
                import msvcrt
                stream.seek(0);stream.write(b'0');stream.flush();stream.seek(0)
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError('ttools или приложение уже работает. Штатно закройте его перед обновлением.') from None
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                fcntl.flock(stream,fcntl.LOCK_UN)

def fetch(url,target,limit=MAX_ARCHIVE):
    if urllib.parse.urlsplit(url).scheme != 'https':
        raise ValueError('Downloads require HTTPS')
    request=urllib.request.Request(url,headers={'User-Agent':'ttools/1.1','Accept':'application/vnd.github+json' if 'api.github.com' in url else '*/*'})
    with urllib.request.urlopen(request,timeout=15) as response, Path(target).open('wb') as output:
        if urllib.parse.urlsplit(response.geturl()).scheme != 'https':
            raise ValueError('Insecure download redirect')
        total=0
        while True:
            chunk=response.read(1024*1024)
            if not chunk:break
            total+=len(chunk)
            if total>limit:raise ValueError('Download exceeds size limit')
            output.write(chunk)

def read_remote_json(url):
    with tempfile.TemporaryDirectory(prefix='ttools-manifest-') as folder:
        path=Path(folder)/'manifest.json'
        fetch(url,path,2*1024*1024)
        return json.loads(path.read_text(encoding='utf-8'))

def extract_zip(archive,directory):
    directory=Path(directory).resolve()
    with zipfile.ZipFile(archive) as package:
        entries=package.infolist()
        if len(entries)>50000 or sum(x.file_size for x in entries)>2*1024**3:
            raise ValueError('Archive extraction limits exceeded')
        for item in entries:
            name=item.orig_filename
            path=PurePosixPath(name)
            mode=item.external_attr>>16
            if (not name or '\0' in name or '\\' in name or ':' in name or name.startswith('/') or path.is_absolute() or '..' in path.parts
                or stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR)):
                raise ValueError(f'Unsafe archive member: {name}')
            dest=directory.joinpath(*path.parts)
            if not dest.resolve().is_relative_to(directory):
                raise ValueError('Archive escapes extraction directory')
            if item.is_dir():
                dest.mkdir(parents=True,exist_ok=True)
            else:
                dest.parent.mkdir(parents=True,exist_ok=True)
                with package.open(item) as source,dest.open('wb') as target:
                    import shutil
                    shutil.copyfileobj(source,target)
                dest.chmod(0o755 if mode&0o111 else 0o644)

def verify_bundle(root):
    root=Path(root).resolve()
    manifest=json.loads((root/'bundle.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version')!=1 or manifest.get('app_id')!='ttools':
        raise ValueError('Invalid suite bundle')
    if not re.fullmatch(r'[0-9A-Za-z._-]+',manifest.get('version','')):
        raise ValueError('Invalid suite version')
    for name,expected in manifest['files'].items():
        path=(root/name).resolve()
        if not path.is_relative_to(root) or not re.fullmatch(r'[a-f0-9]{64}',expected) or not path.is_file() or digest(path)!=expected:
            raise ValueError(f'Bundle checksum mismatch: {name}')
    # Every executable/code/data file must be covered, not just a selected subset.
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p!=root/'bundle.json' and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    if actual!=set(manifest['files']):
        raise ValueError('Bundle contains unlisted files')
    return manifest
