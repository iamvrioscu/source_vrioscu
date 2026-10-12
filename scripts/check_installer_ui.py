"""Isolated browser QA for direct upload progress, retry, draft and publication."""
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('LOG_LEVEL','CRITICAL')
from app import create_app
from app.db import connect, transaction
from app.repositories import Repositories
from tests.test_installer_uploads import inert_pe
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server


def main():
    output = Path(__file__).resolve().parent.parent/'tmp'/'installer-ui'
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vrioscu-installer-ui-') as temporary:
        root = Path(temporary)
        app = create_app({'env':'test','database_path':root/'site.db','release_storage_path':root/'persistent',
                          'base_url':'http://localhost','secret_key':'isolated-browser-test-'*3})
        server = make_server('127.0.0.1',0,app,threaded=True)
        origin = f'http://127.0.0.1:{server.server_port}'
        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        fixture = root/'VRIOSCU Browser Test.exe'; fixture.write_bytes(inert_pe(9*1024**2))
        results=[]; errors=[]
        try:
            with sync_playwright() as p:
                executable = Path(os.environ['LOCALAPPDATA'])/'ms-playwright/chromium_headless_shell-1179/chrome-win/headless_shell.exe'
                browser = p.chromium.launch(executable_path=str(executable),headless=True)
                context = browser.new_context(viewport={'width':1440,'height':1100})
                context.route('**/*',lambda route: route.continue_() if route.request.url.startswith(origin+'/') else route.abort())
                page=context.new_page(); page.on('pageerror',lambda error: errors.append(str(error)))
                page.goto(origin+'/register')
                page.locator('[name=username]').fill('browseradmin')
                page.locator('[name=email]').fill('browser@example.com')
                page.locator('[name=password]').fill('correct horse battery staple!')
                page.locator('[name=accept_privacy]').check()
                page.locator('button[type=submit]').click(); page.wait_for_url(lambda url: str(url).startswith(origin+'/account'))
                conn=connect(root/'site.db'); repos=Repositories(conn)
                with transaction(conn): repos.users.set_role(repos.users.get_by_login('browseradmin')['id'],'admin')
                conn.close()
                page.goto(origin+'/admin/releases/new')
                for width in (1440,390,320):
                    page.set_viewport_size({'width':width,'height':1100})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),width
                    assert page.locator('[data-release-save]').is_disabled()
                    page.screenshot(path=str(output/f'upload-{width}.png'),full_page=True)
                    results.append({'width':width,'overflow':False})
                page.set_viewport_size({'width':1440,'height':1100})
                failed=[False]
                def interrupt(route):
                    if route.request.method=='PUT' and not failed[0]:
                        failed[0]=True
                        response=route.fetch()
                        assert response.status==200
                        route.fulfill(status=503,content_type='application/json',body=json.dumps({'error':{'message':'Simulated lost acknowledgement. Retry to resume.'}}))
                    else: route.continue_()
                page.route('**/api/v1/admin/release-uploads/*',interrupt)
                page.locator('#installer-file').set_input_files(str(fixture))
                page.locator('[data-upload-start]').click()
                page.locator('[data-upload-status]').filter(has_text='Simulated lost acknowledgement').wait_for(timeout=30000)
                assert page.locator('[data-release-save]').is_disabled()
                page.reload()
                page.locator('#installer-file').set_input_files(str(fixture))
                assert page.locator('[data-upload-start]').inner_text()=='Resume upload'
                page.locator('[data-upload-start]').click()
                try:
                    page.locator('[data-upload-status]').filter(has_text='Installer saved and verified').wait_for(timeout=30000)
                except Exception:
                    page.screenshot(path=str(output/'failure.png'),full_page=True)
                    print('Upload UI status:',page.locator('[data-upload-status]').inner_text())
                    raise
                assert page.locator('progress').get_attribute('value')=='100'
                # A verified but unsaved installer survives a tab refresh too.
                page.reload(); page.locator('#installer-file').set_input_files(str(fixture))
                assert page.locator('[data-upload-start]').inner_text()=='Resume upload'
                page.locator('[data-upload-start]').click()
                page.locator('[data-upload-status]').filter(has_text='Installer saved and verified').wait_for(timeout=30000)
                page.locator('[name=version]').fill('99.1.0')
                page.locator('[name=release_date]').fill('2026-10-12')
                page.locator('[data-release-save]').click(); page.wait_for_url('**/admin/releases/*')
                rid=page.url.rsplit('/',1)[1]
                assert context.request.get(origin+'/download/'+rid).status==404
                page.locator('[name=is_published]').check()
                page.locator('[data-release-save]').click(); page.wait_for_url('**/admin/releases')
                response=context.request.get(origin+'/download/'+rid,headers={'Range':'bytes=128-133'})
                assert response.status==206 and response.body()==b'PE\0\0\x64\x86'
                page.goto(origin+'/admin/releases/'+rid)
                page.screenshot(path=str(output/'published.png'),full_page=True)
                assert not errors,errors
                browser.close()
            print(json.dumps({'passed':True,'layouts':results,'bytes':fixture.stat().st_size,'lost_ack_retry':True,
                              'refresh_resume':True,'verified_refresh_resume':True,'draft_publish':True,'range':True,'page_errors':errors}))
        finally:
            server.shutdown(); thread.join(); server.server_close()


if __name__=='__main__': main()
