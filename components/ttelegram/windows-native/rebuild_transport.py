"""Rebuild the reviewable pure-Python TDLib transport fork from vendored sources."""
from pathlib import Path
import zipfile,hashlib,base64,csv,io
root=Path(__file__).resolve().parent
out=root/'wheels/python_telegram-2.0.0+ttnative.1-py3-none-any.whl'
with zipfile.ZipFile(out) as old:
    entries={n:old.read(n) for n in old.namelist() if '.dist-info/' in n and not n.endswith('/RECORD')}
for p in (root/'source/vendor/python-telegram/telegram').rglob('*'):
    if p.is_file() and (p.suffix=='.py' or p.name=='py.typed'):entries['telegram/'+p.name]=p.read_bytes()
rows=[[n,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(b).digest()).decode().rstrip('='),str(len(b))] for n,b in sorted(entries.items())]
record='python_telegram-2.0.0+ttnative.1.dist-info/RECORD';rows.append([record,'','']);buffer=io.StringIO();csv.writer(buffer,lineterminator='\n').writerows(rows);entries[record]=buffer.getvalue().encode()
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
    for n,b in sorted(entries.items()):
        info=zipfile.ZipInfo(n,date_time=(2026,11,18,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(info,b)
print(out.name)
