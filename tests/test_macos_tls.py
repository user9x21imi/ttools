"""Exercise bootstrap/runtime TLS with an initially empty trust store."""
import contextlib
import http.server
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
import bootstrap
from ttools import distribution

MODULES=(bootstrap,distribution)
def empty_store():return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

class ContextTests(unittest.TestCase):
    def test_mac_roots_are_added_without_disabling_validation(self):
        for module in MODULES:
            context=ssl.create_default_context()
            with self.subTest(module=module.__name__),patch.object(module.platform,'system',return_value='Darwin'),patch.object(module.ssl,'create_default_context',return_value=context),patch.object(module.Path,'is_file',return_value=True),patch.dict(os.environ,{'SSL_CERT_FILE':'','SSL_CERT_DIR':''}),patch.object(context,'load_verify_locations') as load:
                actual=module.https_context()
                load.assert_called_once_with(cafile=module.MACOS_CA_BUNDLE)
                self.assertTrue(actual.check_hostname)
                self.assertEqual(actual.verify_mode,ssl.CERT_REQUIRED)

    def test_explicit_ca_overrides_are_not_replaced(self):
        for module in MODULES:
            for key in ('SSL_CERT_FILE','SSL_CERT_DIR'):
                context=ssl.create_default_context()
                with self.subTest(module=module.__name__,key=key),patch.object(module.platform,'system',return_value='Darwin'),patch.object(module.ssl,'create_default_context',return_value=context),patch.dict(os.environ,{key:'/explicit/custom/ca'}),patch.object(context,'load_verify_locations') as load:
                    module.https_context();load.assert_not_called()

    def test_other_platforms_keep_their_default_trust_store(self):
        for module in MODULES:
            context=ssl.create_default_context()
            with patch.object(module.platform,'system',return_value='Linux'),patch.object(module.ssl,'create_default_context',return_value=context),patch.object(context,'load_verify_locations') as load:
                self.assertIs(module.https_context(),context);load.assert_not_called()

@unittest.skipUnless(shutil.which('openssl'),'OpenSSL CLI required to create temporary test certificates')
class HTTPSIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory(prefix='ttools-tls-');cls.root=Path(cls.folder.name)
        for name in ('trusted','other'):
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(cls.root/(name+'.key')),'-out',str(cls.root/(name+'.pem')),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200);self.end_headers();self.wfile.write(b'{"verified":true}')
            def log_message(self,*args):pass
        cls.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cls.root/'trusted.pem'),str(cls.root/'trusted.key'))
        cls.server.socket=context.wrap_socket(cls.server.socket,server_side=True)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url='https://localhost:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=3);cls.folder.cleanup()
    def mac_context(self,module,ca):
        stack=contextlib.ExitStack()
        stack.enter_context(patch.object(module.platform,'system',return_value='Darwin'))
        stack.enter_context(patch.object(module,'MACOS_CA_BUNDLE',str(self.root/ca)))
        stack.enter_context(patch.object(module.ssl,'create_default_context',side_effect=empty_store))
        stack.enter_context(patch.dict(os.environ,{'SSL_CERT_FILE':'','SSL_CERT_DIR':''}))
        return stack
    def test_empty_python_store_is_repaired_for_both_download_paths(self):
        with self.assertRaises(urllib.error.URLError):urllib.request.urlopen(self.url,context=empty_store())
        with self.mac_context(bootstrap,'trusted.pem'):
            self.assertEqual(bootstrap.read(self.url,1024),b'{"verified":true}')
        with self.mac_context(distribution,'trusted.pem'):
            target=self.root/'download.json';distribution.fetch(self.url,target,1024)
            self.assertEqual(target.read_bytes(),b'{"verified":true}')
    def test_unknown_certificate_is_still_rejected(self):
        for module in MODULES:
            with self.subTest(module=module.__name__),self.mac_context(module,'other.pem'),self.assertRaises(urllib.error.URLError):
                if module is bootstrap:module.read(self.url,1024)
                else:module.fetch(self.url,self.root/'untrusted',1024)
    def test_valid_certificate_for_the_wrong_host_is_rejected(self):
        url=self.url.replace('localhost','127.0.0.1')
        with self.mac_context(bootstrap,'trusted.pem'),self.assertRaises(urllib.error.URLError):bootstrap.read(url,1024)
        with self.mac_context(distribution,'trusted.pem'),self.assertRaises(urllib.error.URLError):distribution.fetch(url,self.root/'wrong-host',1024)
    def test_download_size_limits_still_apply(self):
        with self.mac_context(bootstrap,'trusted.pem'),self.assertRaises(ValueError):bootstrap.read(self.url,3)
        with self.mac_context(distribution,'trusted.pem'),self.assertRaises(ValueError):distribution.fetch(self.url,self.root/'limited',3)
if __name__=='__main__':unittest.main()
