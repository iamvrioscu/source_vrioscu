import hashlib
import io
import os
import shutil
import struct
from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.services.installers import CHUNK_BYTES, InstallerStore
from tests.helpers import AppTestCase

URL = '/api/v1/admin/release-uploads'


def inert_pe(size=4096):
    """Non-runnable test bytes with the signatures inspected by the upload validator."""
    data = bytearray(size)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 128)
    data[128:134] = b'PE\0\0\x64\x86'
    return bytes(data)


class InstallerUploadTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.h = self.api_headers(self.admin)
        self.store = InstallerStore(self.app.config['SETTINGS'])

    def start(self, data=None, filename='VRIOSCU Setup.exe'):
        data = data or inert_pe()
        response = self.admin.post(URL, json={'filename': filename, 'size': len(data)}, headers=self.h)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()['id']

    def chunk(self, upload_id, data, offset=0):
        return self.admin.put(URL+'/'+upload_id, data=data, headers={**self.h,'Upload-Offset':str(offset)}, content_type='application/octet-stream')

    def uploaded(self, data=None):
        data = data or inert_pe()
        upload_id = self.start(data)
        self.assertEqual(self.chunk(upload_id,data).status_code,200)
        response = self.admin.post(URL+'/'+upload_id+'/complete',headers=self.h)
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(response.get_json()['state'],'verified')
        return upload_id

    def draft(self, upload_id=None, **extra):
        payload = self.release_payload(upload_id=upload_id or self.uploaded(),is_published=False,**extra)
        for key in ('sha256','download_url','installer_filename','file_size_bytes'):
            payload.pop(key,None)
        response = self.admin.post('/api/v1/admin/releases',json=payload,headers=self.h)
        self.assertEqual(response.status_code,201,response.get_json())
        return response.get_json()['release']['id']

    def publish(self, release_id):
        response = self.admin.patch('/api/v1/admin/releases/'+str(release_id),json={'is_published':True},headers=self.h)
        self.assertEqual(response.status_code,200,response.get_json())
        return response

    def test_upload_metadata_draft_publish_download_and_range(self):
        data = inert_pe()
        uid = self.uploaded(data)
        conn,r = self.repos()
        upload = r.uploads.get(uid)
        self.assertEqual(upload['sha256'],hashlib.sha256(data).hexdigest())
        self.assertEqual(upload['received_bytes'],len(data))
        self.assertTrue(upload['updated_at'].endswith('Z'))
        conn.close()
        rid = self.draft(uid)
        self.assertEqual(self.client.get('/download/'+str(rid)).status_code,404)
        self.publish(rid)
        response = self.client.get('/download/'+str(rid))
        self.assertEqual(response.data,data)
        self.assertEqual(response.content_type,'application/octet-stream')
        self.assertEqual(response.content_length,len(data))
        self.assertIn('attachment',response.headers['Content-Disposition'])
        self.assertIn('VRIOSCU Setup.exe',response.headers['Content-Disposition'])
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        response.close()
        response = self.client.get('/download/'+str(rid),headers={'Range':'bytes=128-133'})
        self.assertEqual(response.status_code,206)
        self.assertEqual(response.data,data[128:134])
        self.assertEqual(response.headers['Content-Range'],f'bytes 128-133/{len(data)}')
        response.close()
        latest = self.client.get('/download/latest')
        self.assertEqual(latest.data,data); latest.close()
        html = self.client.get('/download').get_data(as_text=True)
        self.assertNotIn(hashlib.sha256(data).hexdigest(),html)
        self.assertNotIn(str(self.store.root),html)

    def test_explicit_publication_requires_saved_draft(self):
        uid = self.uploaded()
        response = self.admin.post('/api/v1/admin/releases',json=self.release_payload(upload_id=uid),headers=self.h)
        self.assertEqual(response.status_code,422)
        rid = self.draft(uid)
        self.publish(rid)

    def test_unauthenticated_nonadmin_csrf_and_upload_ownership(self):
        anon = self.app.test_client()
        self.assertEqual(anon.post(URL,json={'filename':'a.exe','size':4096},headers={'X-CSRF-Token':self.csrf(anon)}).status_code,401)
        self.register()
        self.assertEqual(self.client.post(URL,json={'filename':'a.exe','size':4096},headers=self.api_headers(self.client)).status_code,403)
        self.assertEqual(self.admin.post(URL,json={'filename':'a.exe','size':4096}).status_code,400)
        uid = self.start()
        other = self.make_admin('secondadmin','second@example.com')
        headers = self.api_headers(other)
        for method,path in (('get',''),('put',''),('delete',''),('post','/complete')):
            response = getattr(other,method)(URL+'/'+uid+path,headers=headers)
            self.assertIn(response.status_code,(404,415,400))
        self.assertEqual(other.post('/api/v1/admin/releases',json=self.release_payload(upload_id=uid,is_published=False),headers=headers).status_code,404)

    def test_invalid_filename_extension_size_and_paths(self):
        for name in ('../a.exe','a.exe/evil','a.exe\\evil','a.exe\r\nHeader: injected','a.bat','a.exe:evil','..exe','CON.exe','NUL.exe','COM1.exe','a'*125+'.exe'):
            self.assertEqual(self.admin.post(URL,json={'filename':name,'size':4096},headers=self.h).status_code,422,name)
        for size in (0,127,True,'4096',9*1024**3):
            self.assertEqual(self.admin.post(URL,json={'filename':'a.exe','size':size},headers=self.h).status_code,422)
        for path in ('../secret','a'*32+'.exe','f'*31):
            self.assertEqual(self.admin.get(URL+'/'+path).status_code,404)
        self.assertEqual(self.client.get('/_protected_installers/'+'f'*32+'.exe').status_code,404)

    def test_exe_header_validation(self):
        for data in (b'x'*4096, b'MZ'+b'\0'*4094, inert_pe()[:128]+b'BAD!!!'+inert_pe()[134:]):
            uid = self.start(data)
            self.assertEqual(self.chunk(uid,data).status_code,200)
            self.assertEqual(self.admin.post(URL+'/'+uid+'/complete',headers=self.h).status_code,422)
            self.assertFalse(self.store.path(uid+'.exe').exists())
            self.admin.delete(URL+'/'+uid,headers=self.h)

    def test_retry_progress_and_resume_after_restart(self):
        data = inert_pe()
        uid = self.start(data)
        self.assertEqual(self.chunk(uid,data[:2048]).get_json()['received_bytes'],2048)
        self.assertEqual(self.chunk(uid,data[:2048]).get_json()['received_bytes'],2048)
        self.assertEqual(self.chunk(uid,b'x'*2048).status_code,409)
        self.assertEqual(self.chunk(uid,data[2048:],3000).status_code,409)
        self.assertEqual(self.admin.post(URL+'/'+uid+'/complete',headers=self.h).status_code,409)
        # Simulate bytes written before a killed process committed its offset.
        with self.store.stage(uid).open('ab') as f: f.write(b'uncommitted')
        restarted = create_app({'env':'test','database_path':self.db_path,'base_url':self.base_url,'secret_key':'t'*48})
        self.assertEqual(restarted.config['SETTINGS'].release_storage_path,self.store.root)
        self.assertEqual(self.admin.get(URL+'/'+uid).get_json()['received_bytes'],2048)
        self.assertEqual(self.chunk(uid,data[2048:],2048).get_json()['received_bytes'],4096)
        self.assertEqual(self.store.stage(uid).stat().st_size,4096)
        self.assertEqual(self.admin.post(URL+'/'+uid+'/complete',headers=self.h).status_code,200)
        self.assertEqual(self.admin.post(URL+'/'+uid+'/complete',headers=self.h).status_code,200)

    def test_interrupted_stream_rolls_back_chunk(self):
        uid = self.start()
        conn,r = self.repos()
        owner = r.uploads.get(uid)['owner_id']
        with self.assertRaises(Exception):
            self.store.chunk(r,owner,uid,0,io.BytesIO(b'partial'),4096)
        self.assertEqual(r.uploads.get(uid)['received_bytes'],0)
        self.assertEqual(self.store.stage(uid).stat().st_size,0)
        conn.close()

    def test_disk_capacity_reservations_and_during_upload(self):
        with patch('app.services.installers.shutil.disk_usage',return_value=shutil._ntuple_diskusage(100,90,10)):
            response = self.admin.post(URL,json={'filename':'a.exe','size':4096},headers=self.h)
            self.assertEqual(response.status_code,507)
            self.assertIn('storage',response.get_json()['error']['message'])
        uid = self.start()
        with patch('app.services.installers.shutil.disk_usage',return_value=shutil._ntuple_diskusage(100,90,10)):
            self.assertEqual(self.chunk(uid,inert_pe()).status_code,507)

    def test_chunk_size_cap_and_normal_form_limit(self):
        uid = self.start()
        self.assertEqual(self.chunk(uid,b'x'*(CHUNK_BYTES+1)).status_code,413)
        self.assertEqual(self.admin.post(URL,json={'filename':'a.exe','size':4096,'padding':'x'*70000},headers=self.h).status_code,413)

    def test_cancel_expiry_cleanup_and_attached_protection(self):
        uid = self.uploaded()
        self.assertEqual(self.admin.delete(URL+'/'+uid,headers=self.h).status_code,204)
        self.assertFalse(self.store.path(uid+'.exe').exists())
        uid = self.start()
        self.chunk(uid,inert_pe()[:1024])
        conn,r = self.repos()
        conn.execute("UPDATE release_uploads SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",(uid,))
        self.assertEqual(self.store.cleanup(r),1)
        self.assertFalse(self.store.stage(uid).exists())
        conn.close()
        uid = self.uploaded(); self.draft(uid)
        self.assertEqual(self.admin.delete(URL+'/'+uid,headers=self.h).status_code,409)
        self.assertTrue(self.store.path(uid+'.exe').exists())

    def test_tampered_missing_unpublished_deleted_and_persistence(self):
        uid = self.uploaded(); rid = self.draft(uid)
        path = self.store.path(uid+'.exe')
        data = path.read_bytes(); path.write_bytes(data[:-1]+b'x')
        self.assertEqual(self.admin.patch('/api/v1/admin/releases/'+str(rid),json={'is_published':True},headers=self.h).status_code,422)
        path.write_bytes(data); self.publish(rid)
        restarted = create_app({'env':'test','database_path':self.db_path,'base_url':self.base_url,'secret_key':'t'*48})
        response = restarted.test_client().get('/download/'+str(rid)); self.assertEqual(response.data,data); response.close()
        self.admin.patch('/api/v1/admin/releases/'+str(rid),json={'is_published':False},headers=self.h)
        self.assertEqual(self.client.get('/download/'+str(rid)).status_code,404)
        self.publish(rid)
        self.admin.delete('/api/v1/admin/releases/'+str(rid),headers=self.h)
        self.assertEqual(self.client.get('/download/'+str(rid)).status_code,404)
        self.assertTrue(path.exists(),'Deleting metadata retains the installer for recovery')

    def test_unique_files_and_duplicate_attachment(self):
        first = self.uploaded(); rid = self.draft(first); self.publish(rid)
        second = self.uploaded()
        self.assertNotEqual(first,second)
        self.assertTrue(self.store.path(first+'.exe').exists())
        self.assertEqual(self.admin.post('/api/v1/admin/releases',json=self.release_payload(upload_id=first,version='2.0.0',is_published=False),headers=self.h).status_code,422)

    def test_nginx_internal_delivery_headers(self):
        uid = self.uploaded(); rid = self.draft(uid); self.publish(rid)
        self.app.config['SETTINGS'].release_x_accel = True
        response = self.client.get('/download/'+str(rid))
        self.assertEqual(response.headers['X-Accel-Redirect'],'/_protected_installers/'+uid+'.exe')
        self.assertIn('attachment',response.headers['Content-Disposition'])
        self.assertEqual(response.data,b'')

    def test_https_generated_link_and_ui(self):
        self.app.config['SETTINGS'].base_url='https://vrioscu.example'
        uid = self.uploaded(); rid = self.draft(uid)
        response = self.publish(rid)
        self.assertEqual(response.get_json()['release']['download_url'],f'https://vrioscu.example/download/{rid}')
        html = self.admin.get('/admin/releases/'+str(rid)).get_data(as_text=True)
        self.assertIn(f'https://vrioscu.example/download/{rid}',html)
        self.assertNotIn('name="download_url"',html)
        self.assertNotIn('name="sha256"',html)
        self.assertIn('type="file"',html)

    def test_backup_bundle_restores_matching_database_and_installer(self):
        import json
        from scripts.backup_installers import backup
        uid = self.uploaded(); rid = self.draft(uid); self.publish(rid)
        bundle = backup(Path(self.db_path),self.store.root,Path(self.tmp)/'backups')
        manifest = json.loads((bundle/'manifest.json').read_text())
        self.assertEqual(manifest['installers'][0]['storage_key'],uid+'.exe')
        restored_root = Path(self.tmp)/'restored'; restored_root.mkdir()
        shutil.copyfile(bundle/'vrioscu.db',restored_root/'site.db')
        shutil.copytree(bundle/'objects',restored_root/'persistent'/'objects')
        restored = create_app({'env':'test','database_path':restored_root/'site.db','release_storage_path':restored_root/'persistent',
                               'base_url':self.base_url,'secret_key':'t'*48})
        response = restored.test_client().get('/download/'+str(rid))
        try:
            self.assertEqual(response.data,inert_pe())
        finally:
            response.close()

    def test_missing_file_is_not_listed_or_downloaded(self):
        uid = self.uploaded(); rid = self.draft(uid); self.publish(rid)
        self.store.path(uid+'.exe').unlink()
        self.assertEqual(self.client.get('/download/'+str(rid)).status_code,404)
        self.assertIn('Coming Soon',self.client.get('/download').get_data(as_text=True))
        self.assertEqual(self.client.get('/api/v1/releases/latest').status_code,404)

    def test_unsatisfiable_range_and_head_size(self):
        uid = self.uploaded(); rid = self.draft(uid); self.publish(rid)
        response = self.client.get('/download/'+str(rid),headers={'Range':'bytes=999999-'})
        self.assertEqual(response.status_code,416)
        self.assertEqual(response.headers['Content-Range'],'bytes */4096')
        response.close()
        response = self.client.head('/download/'+str(rid))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.content_length,4096)
        self.assertEqual(response.data,b'')
        response.close()

    def test_storage_key_cannot_escape_private_directory(self):
        from werkzeug.exceptions import NotFound
        for key in ('../secret.exe','C:\\secret.exe','/etc/passwd','f'*32+'.exe/../secret'):
            with self.assertRaises(NotFound):
                self.store.path(key)
        target = Path(self.tmp)/'outside.exe'; target.write_bytes(inert_pe())
        self.store.prepare()
        link = self.store.root/'objects'/('f'*32+'.exe')
        try:
            link.symlink_to(target)
        except OSError:
            return  # Windows may not grant CreateSymbolicLink; key checks still ran.
        with self.assertRaises(NotFound): self.store.path(link.name)
        self.assertEqual(target.read_bytes(),inert_pe())
