"""Catalogs contain trusted argv, never shell fragments."""
import json
import os
from pathlib import Path
import re
import shutil
import urllib.request

CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'ttools'

def read_catalog(path):
    path = Path(path).expanduser().resolve()
    if path.is_dir():
        path = path/'apps.local.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('apps'), list):
        raise ValueError('Ожидается объект с массивом apps')
    apps = []
    for entry in data['apps']:
        app = dict(entry)
        if not isinstance(app.get('id'), str) or not re.fullmatch(r'[\w-]+', app['id']):
            raise ValueError('Некорректный id приложения')
        argv = app.get('command')
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
            raise ValueError(f"{app['id']}: command должен быть массивом аргументов")
        argv = [os.path.expandvars(os.path.expanduser(a)) for a in argv]
        if '/' in argv[0] and not Path(argv[0]).is_absolute():
            argv[0] = str(path.parent/argv[0])
        app['command'] = argv
        app['_catalog'] = str(path)
        apps.append(app)
    return apps

def sources():
    path = CONFIG/'sources.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []

def add_source(path):
    path = Path(path).expanduser().resolve()
    if path.is_dir():
        path /= 'apps.local.json'
    read_catalog(path)
    values = sources()
    if str(path) not in values:
        values.append(str(path))
    CONFIG.mkdir(parents=True, exist_ok=True)
    temp = CONFIG/'sources.tmp'
    temp.write_text(json.dumps(values, ensure_ascii=False, indent=2),encoding='utf-8')
    temp.replace(CONFIG/'sources.json')

def _dev_catalog_path():
    """Return path to a development apps.local.json if running from source tree."""
    # Check if we're in the ttools source tree by looking for component directories
    here = Path(__file__).resolve()
    # ttools/core.py -> parents[1] = repo root (ttools-integration/)
    repo_root = here.parents[1]
    components = repo_root/'components'
    if not components.is_dir():
        return None
    # Check for at least one component source directory
    if not any((components/c/'source').is_dir() for c in ('tspotify','tthings','tvpn','ttelegram','tsoundcloud')):
        return None
    # Look for a pre-generated dev catalog at repo root
    dev_catalog = repo_root/'apps.local.json'
    if dev_catalog.is_file():
        return dev_catalog
    return None

def load_apps():
    merged, errors = {}, []
    managed = os.environ.get('TTOOLS_CATALOG')
    # User sources and managed catalog take priority
    for path in sources() + ([managed] if managed else []):
        try:
            for app in read_catalog(path):
                merged[app['id']] = app
        except (OSError, ValueError, TypeError) as e:
            errors.append(f'{path}: {e}')
    # Fallback: development catalog from source tree (only if no apps loaded yet)
    if not merged and not managed and not sources():
        dev_path = _dev_catalog_path()
        if dev_path:
            try:
                for app in read_catalog(dev_path):
                    merged[app['id']] = app
            except (OSError, ValueError, TypeError) as e:
                errors.append(f'{dev_path}: {e}')
    order = {'tspotify':0, 'tsoundcloud':1, 'soundcloud':1, 'tyoutube':2, 'youtube':2, 'ttelegram':3, 'tvpn':4, 'tthings':5}
    return sorted(merged.values(), key=lambda app: order.get(app['id'], 6)), errors

def available(app):
    exe = app['command'][0]
    return bool(shutil.which(exe))

def check_update(app):
    if app.get('suite_managed'):
        return 'Обновляет '+('TVPN' if app.get('update_owner')=='tvpn' else 'ttools')+' · ' + app.get('version','')
    repo = app.get('repository') or ''
    match = re.fullmatch(r'https://github.com/([\w.-]+/[\w.-]+?)(?:\.git)?/?', repo)
    if not match:
        return 'Нет источника обновлений'
    slug = match[1]
    commit = app.get('source_commit')
    endpoint = f'https://api.github.com/repos/{slug}/' + ('commits?per_page=1' if commit else 'releases/latest')
    request = urllib.request.Request(endpoint, headers={'User-Agent':'ttools/1.0', 'Accept':'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.load(response)
        if commit:
            return 'Исходники актуальны' if data[0]['sha'] == commit else 'Есть изменения исходников'
        remote = data['tag_name'].lstrip('v')
        local = app.get('version')
        if not local:
            return f'Релиз {remote} · локальная версия неизвестна'
        return 'Актуальная версия' if local.lstrip('v') == remote else f'Релиз {remote} · локально {local}'
    except Exception as e:
        return f'Проверка недоступна ({getattr(e, "code", type(e).__name__)})'
