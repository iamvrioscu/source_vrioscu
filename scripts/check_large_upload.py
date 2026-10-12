#!/usr/bin/env python3
"""Opt-in >200 MiB upload integration using inert fixture bytes, never executed.

Runs a real local HTTP server with an isolated database and persistent directory.
Verifies chunk retry, progress, publish, full download hash, range and app restart.
Temporary files are outside the checkout and removed when the check finishes.
"""
import hashlib
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('LOG_LEVEL','CRITICAL')
from app import create_app  # noqa: E402
from app.db import connect, transaction  # noqa: E402
from app.repositories import Repositories  # noqa: E402
from tests.test_installer_uploads import inert_pe  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402


def main():
    size = 205 * 1024**2 + 123
    with tempfile.TemporaryDirectory(prefix='vrioscu-large-upload-') as temporary:
        root = Path(temporary)
        options = {'env':'test','database_path':root/'site.db','release_storage_path':root/'persistent',
                   'base_url':'http://localhost','secret_key':'isolated-integration-'*3}
        app = create_app(options)
        server = make_server('127.0.0.1',0,app,threaded=True)
        origin = f'http://127.0.0.1:{server.server_port}'
        worker = threading.Thread(target=server.serve_forever,daemon=True); worker.start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(CookieJar()))
        def req(path,method='GET',body=None,headers=None):
            if isinstance(body,dict):
                body = json.dumps(body).encode(); headers = {'Content-Type':'application/json',**(headers or {})}
            response = opener.open(urllib.request.Request(origin+path,data=body,method=method,headers=headers or {}),timeout=300)
            return response
        try:
            import re
            with req('/register') as response: token = re.search(r'name="csrf-token" content="([^"]+)"',response.read().decode()).group(1)
            payload = urllib.parse.urlencode({'username':'integrationadmin','email':'integration@example.com','password':'correct horse battery staple!','accept_privacy':'1','csrf_token':token}).encode()
            with req('/register','POST',payload,{'Content-Type':'application/x-www-form-urlencoded'}): pass
            conn = connect(root/'site.db'); repos = Repositories(conn)
            with transaction(conn): repos.users.set_role(repos.users.get_by_login('integrationadmin')['id'],'admin')
            conn.close()
            with req('/api/v1/me') as response: headers = {'X-CSRF-Token':json.load(response)['csrf_token']}
            endpoint = '/api/v1/admin/release-uploads'
            with req(endpoint,'POST',{'filename':'VRIOSCU-Large-Test.exe','size':size},headers) as response: uid = json.load(response)['id']
            sha = hashlib.sha256(); offset = 0; chunks = 0
            while offset < size:
                length = min(8*1024**2,size-offset)
                block = inert_pe(length) if offset == 0 else b'\0'*length
                chunk_headers = {**headers,'Content-Type':'application/octet-stream','Upload-Offset':str(offset)}
                with req(endpoint+'/'+uid,'PUT',block,chunk_headers) as response: result = json.load(response)
                if offset == 0:
                    with req(endpoint+'/'+uid,'PUT',block,chunk_headers) as response: assert json.load(response)['received_bytes'] == length
                sha.update(block); offset += length; chunks += 1
                assert result['received_bytes'] == offset
            with req(endpoint+'/'+uid+'/complete','POST',{},headers) as response: assert json.load(response)['state'] == 'verified'
            payload = {'upload_id':uid,'version':'99.0.0','channel':'PUBLIC_BETA','release_date':'2026-10-12','is_published':False}
            with req('/api/v1/admin/releases','POST',payload,headers) as response: rid = json.load(response)['release']['id']
            with req('/api/v1/admin/releases/'+str(rid),'PATCH',{'is_published':True},headers): pass
            received = hashlib.sha256(); count = 0
            with req('/download/'+str(rid)) as response:
                assert int(response.headers['Content-Length']) == size
                assert 'attachment' in response.headers['Content-Disposition']
                while block := response.read(1024**2): received.update(block); count += len(block)
            assert count == size and received.hexdigest() == sha.hexdigest()
            with req('/download/'+str(rid),headers={'Range':'bytes=128-133'}) as response:
                assert response.status == 206 and response.read() == b'PE\0\0\x64\x86'
            # Fresh app instance, same external storage and DB, models a replaced checkout.
            restarted = create_app(options)
            response = restarted.test_client().get('/download/'+str(rid),headers={'Range':f'bytes={size-123}-{size-1}'})
            try:
                assert response.status_code == 206 and len(response.data) == 123
            finally:
                response.close()
            print(json.dumps({'passed':True,'bytes':size,'chunks':chunks,'retry':True,'sha256_verified':True,'range':True,'restart_persistence':True}))
        finally:
            server.shutdown(); worker.join(); server.server_close()


if __name__ == '__main__':
    main()
