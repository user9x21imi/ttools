"""macOS CI: exercise real system roots with an otherwise empty Python store."""
import os
from pathlib import Path
import platform
import ssl
import sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bootstrap
from ttools import distribution
if platform.system()!='Darwin':raise SystemExit('macOS-only smoke check')
assert Path('/etc/ssl/cert.pem').is_file()
def empty():return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
url='https://raw.githubusercontent.com/user9x21imi/ttools/main/ttools/__init__.py'
with patch.dict(os.environ,{'SSL_CERT_FILE':'','SSL_CERT_DIR':''}),patch('ssl.create_default_context',side_effect=empty):
    context=bootstrap.https_context()
    assert context.cert_store_stats()['x509_ca']>0
    assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
    data=bootstrap.read(url,8192)
    assert b'__version__' in data
    runtime=distribution.https_context()
    assert runtime.cert_store_stats()['x509_ca']>0
print('macOS system CA bundle: trusted HTTPS download passed with initially empty Python roots')
