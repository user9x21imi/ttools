"""Verified downloads, cross-platform locking and atomic installation metadata."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import ssl
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

REPOSITORY = 'user9x21imi/ttools'
MAX_ARCHIVE = 700 * 1024 * 1024

MACOS_CA_BUNDLE = '/etc/ssl/cert.pem'

def https_context():
    """Keep TLS validation enabled and add macOS system roots when appropriate.

    python.org builds can have an empty OpenSSL store until the separate
    certificate-install step is run. Explicit CA overrides remain authoritative.
    This small helper is also present in the standalone bootstrap, which must
    work before the ttools package has been downloaded.
    """
    context=ssl.create_default_context()
    if (platform.system()=='Darwin'
            and not any(os.environ.get(key) for key in ('SSL_CERT_FILE','SSL_CERT_DIR'))
            and Path(MACOS_CA_BUNDLE).is_file()):
        context.load_verify_locations(cafile=MACOS_CA_BUNDLE)
    return context


def configure_text_io():
    if os.name=='nt':
        os.environ['PYTHONUTF8']='1'
        os.environ['PYTHONIOENCODING']='utf-8'
        for stream in (sys.stdout,sys.stderr):
            if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='replace')


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

SOURCE_COMMIT_RE=re.compile(r'[0-9a-f]{40}')
COMPONENT_IDS=('tspotify','tsoundcloud','ttelegram','tvpn','tthings')

def valid_source_commit(value):
    return isinstance(value,str) and SOURCE_COMMIT_RE.fullmatch(value) is not None

def validate_component_versions(root, strict=False):
    """Check component version declarations before a bundle can be activated."""
    root=Path(root)
    try:versions=json.loads((root/'components/versions.json').read_text(encoding='utf-8'))
    except (OSError,ValueError) as error:raise ValueError('Invalid component version catalog') from error
    if not isinstance(versions,dict) or not versions or any(
            not isinstance(name,str) or not isinstance(value,str) or not value.strip()
            for name,value in versions.items()):
        raise ValueError('Invalid component version catalog')
    if strict and set(versions)!=set(COMPONENT_IDS):
        raise ValueError('Component catalog does not declare the full suite')
    for app,version in versions.items():
        if app not in COMPONENT_IDS:
            raise ValueError(f'Unknown component in version catalog: {app}')
        candidates=(root/'components'/app/'app.json',
                    root/'components'/app/'update.json',
                    root/'components'/app/'source'/'update.json')
        found=False
        for path in candidates:
            if not path.is_file():continue
            try:metadata=json.loads(path.read_text(encoding='utf-8'))
            except ValueError as error:raise ValueError(f'Invalid component metadata: {path.relative_to(root)}') from error
            declared=metadata.get('version') if isinstance(metadata,dict) else None
            if declared is not None:
                found=True
                if declared!=version:
                    raise ValueError(f'Component version mismatch: {app} catalog={version} metadata={declared}')
        if strict and not found:
            raise ValueError(f'Component has no versioned metadata: {app}')
    if strict:
        # Windows Telegram is an explicit platform preview with its own version.
        windows=root/'components/ttelegram/windows-native/app.json'
        if not windows.is_file():raise ValueError('Windows Telegram preview metadata is missing')
        metadata=json.loads(windows.read_text(encoding='utf-8'))
        if not isinstance(metadata.get('version'),str) or not metadata['version'].strip():
            raise ValueError('Windows Telegram preview has no version')
    return versions


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
    with urllib.request.urlopen(request,timeout=15,context=https_context()) as response, Path(target).open('wb') as output:
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

def latest_suite_manifest(preview=False):
    """Read the newest suite manifest without consuming GitHub API quota."""
    namespace='{http://www.w3.org/2005/Atom}'
    with tempfile.TemporaryDirectory(prefix='ttools-release-feed-') as folder:
        path=Path(folder)/'releases.atom'
        fetch(f'https://github.com/{REPOSITORY}/releases.atom',path,2*1024*1024)
        root=ET.parse(path).getroot()
    prefix=f'https://github.com/{REPOSITORY}/releases/tag/'
    for entry in root.findall(namespace+'entry'):
        for link in entry.findall(namespace+'link'):
            href=link.get('href','')
            if not href.startswith(prefix):continue
            tag=urllib.parse.unquote(href[len(prefix):])
            if not re.fullmatch(r'v\d+\.\d+\.\d+(?:-(?:alpha|beta|rc|preview)\.\d+)?',tag):continue
            if not preview and '-' in tag:continue
            manifest_url=f'https://github.com/{REPOSITORY}/releases/download/{urllib.parse.quote(tag,safe="")}/suite-update.json'
            try:manifest=read_remote_json(manifest_url)
            except urllib.error.HTTPError as error:
                if error.code==404:continue
                raise
            if manifest.get('schema_version') not in (1,2) or manifest.get('app_id')!='ttools':
                raise ValueError('Invalid suite update manifest')
            if manifest.get('version')!=tag[1:]:raise ValueError('Release tag/version mismatch')
            if manifest.get('schema_version')==2 and not valid_source_commit(manifest.get('source_commit')):
                raise ValueError('Invalid suite source commit')
            return manifest
    raise RuntimeError('No published suite release in this update channel')

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
    schema=manifest.get('schema_version')
    if schema not in (1,2) or manifest.get('app_id')!='ttools':
        raise ValueError('Invalid suite bundle')
    if not re.fullmatch(r'[0-9A-Za-z._-]+',manifest.get('version','')):
        raise ValueError('Invalid suite version')
    if schema==2:
        version_key(manifest['version'])
        if not valid_source_commit(manifest.get('source_commit')):
            raise ValueError('Invalid suite source commit')
        try:
            import ast
            module=ast.parse((root/'ttools/__init__.py').read_text(encoding='utf-8'))
            bundled_version=next(node.value.value for node in module.body
                if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='__version__' for target in node.targets)
                and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str))
        except (OSError,StopIteration,SyntaxError) as error:
            raise ValueError('Bundle has no readable launcher version') from error
        if bundled_version!=manifest['version']:
            raise ValueError('Bundle launcher/version metadata mismatch')
        validate_component_versions(root,strict=True)
    for name,expected in manifest['files'].items():
        path=(root/name).resolve()
        if not path.is_relative_to(root) or not re.fullmatch(r'[a-f0-9]{64}',expected) or not path.is_file() or digest(path)!=expected:
            raise ValueError(f'Bundle checksum mismatch: {name}')
    # Every executable/code/data file must be covered, not just a selected subset.
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p!=root/'bundle.json' and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    if actual!=set(manifest['files']):
        raise ValueError('Bundle contains unlisted files')
    return manifest
