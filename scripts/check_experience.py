"""End-to-end UI QA using an isolated SQLite fixture and localhost-only browser.

Never changes the running site's database or follows an installer destination.
Run: python scripts/check_experience.py
"""
import argparse
import json
import os
from pathlib import Path
import sys
from datetime import timedelta
from threading import Thread

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from tests.helpers import AppTestCase, PASSWORD
from app.db import transaction
from app.time_utils import utcnow

PUBLIC = ['/', '/product', '/features', '/how-it-works', '/reports', '/documentation',
          '/use-cases', '/download', '/public-beta', '/contact', '/privacy', '/login', '/register']
ADMIN = ['/admin','/admin/analytics','/admin/launch-interest','/admin/users','/admin/subscribers',
         '/admin/feedback','/admin/support','/admin/desktop-submissions','/admin/releases','/admin/exports','/admin/releases/new']
OUT = ROOT / 'tmp/redesign-v2'


def check_layout(page,path,width,theme):
    page.locator('img').evaluate_all("imgs=>imgs.forEach(i=>{if(i.hasAttribute('src'))i.loading='eager'})")
    page.locator('.site-footer').scroll_into_view_if_needed()
    page.wait_for_function('() => Array.from(document.images).filter(i=>i.currentSrc).every(i=>i.complete)')
    broken=page.locator('img').evaluate_all('imgs=>imgs.filter(i=>i.currentSrc&&!i.naturalWidth).map(i=>i.src)')
    assert not broken,(path,broken)
    sizes=page.evaluate('({viewport:innerWidth,doc:document.documentElement.scrollWidth})')
    assert sizes['doc'] <= sizes['viewport'],(path,width,theme,sizes)
    assert page.locator('h1').count()==1,path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--targeted',action='store_true',help='Check the affected public/release layouts and all workflows')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    case=AppTestCase();case.setUp()
    case.make_admin(username='preview_admin',email='preview-admin@example.com')
    case.reset_rate_limits()
    conn,repos=case.repos()
    now=utcnow()
    with transaction(conn):
        for n in range(54):
            repos.launch.register({'first_name':f'Preview {n+1}','last_name':'Registrant','email':f'preview{n+1}@example.com'},'preview')
        for day in range(29,-1,-1):
            for view in range(1,day%7+4):
                repos.analytics.record(f'fixture-{day}-{view}',f'{day:03d}{view:03d}'+'a'*26,
                    PUBLIC[(day+view)%11],'Direct' if view%2 else 'search.example',
                    'Chrome' if view%2 else 'Firefox','Desktop' if view%3 else 'Mobile',
                    now=now-timedelta(days=day,minutes=view))
    conn.close()
    server=make_server('127.0.0.1',0,case.app,threaded=True)
    origin=f'http://127.0.0.1:{server.server_port}'
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    checks=[];errors=[];failed=[]
    rail_checks=[];analytics_requests=[]
    executable=Path(os.environ.get('LOCALAPPDATA',''))/'ms-playwright/chromium_headless_shell-1179/chrome-win/headless_shell.exe'
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,executable_path=str(executable) if executable.exists() else None)
            context=browser.new_context(viewport={'width':1440,'height':1000},color_scheme='dark')
            context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(origin+'/') else route.abort())
            page=context.new_page()
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
            page.on('response',lambda r:failed.append((r.status,r.url)) if r.status>=400 else None)
            page.on('request',lambda r:analytics_requests.append(r.url) if r.url.endswith('/analytics/event') else None)
            # Explicit analytics choice: default off; allowing records one page view.
            page.goto(origin+'/',wait_until='networkidle')
            assert page.locator('[data-consent-banner]').count()==0
            assert not any(c['name']=='vr_analytics' for c in context.cookies())
            page.reload(wait_until='networkidle')
            page.goto(origin+'/product',wait_until='networkidle')
            assert not analytics_requests,'optional analytics must remain off before a settings choice'
            page.get_by_role('link',name='Analytics settings',exact=True).click()
            page.wait_for_url('**/privacy#analytics-privacy',wait_until='networkidle')
            page.get_by_role('button',name='Allow analytics',exact=True).click()
            page.wait_for_url('**/privacy',wait_until='networkidle')
            page.wait_for_function("() => document.body && document.body.dataset.analyticsChoice === 'allow'")
            page.wait_for_timeout(200)
            assert analytics_requests,'existing opt-in still enables first-party analytics'
            page.goto(origin+'/reports',wait_until='networkidle')
            assert page.locator('[data-consent-banner]').count()==0
            page.get_by_role('link',name='Analytics settings',exact=True).click()
            page.wait_for_url('**/privacy#analytics-privacy',wait_until='networkidle')
            page.get_by_role('button',name='Decline / withdraw analytics',exact=True).click()
            page.wait_for_url('**/privacy',wait_until='networkidle')
            page.wait_for_function("() => document.body && document.body.dataset.analyticsChoice === 'decline'")
            requests_after_withdrawal=len(analytics_requests)
            page.goto(origin+'/',wait_until='networkidle')
            assert len(analytics_requests)==requests_after_withdrawal
            for theme in ('dark','light'):
                page.evaluate('(theme)=>{localStorage.setItem("vrioscu-theme",theme);document.documentElement.dataset.theme=theme}',theme)
                for width in ((1440,390,320) if args.targeted else (1440,1024,768,390,320)):
                    page.set_viewport_size({'width':width,'height':1000})
                    for path in (('/', '/reports','/download','/privacy') if args.targeted else PUBLIC):
                        response=page.goto(origin+path,wait_until='networkidle')
                        assert response.status==200,(path,response.status)
                        assert page.locator('html').get_attribute('data-theme')==theme
                        check_layout(page,path,width,theme)
                        checks.append({'path':path,'width':width,'theme':theme})
                        if width in (1440,390) and path in ('/','/reports','/download','/contact','/login'):
                            page.evaluate("scrollTo({top:0,behavior:'instant'})")
                            name=path.strip('/') or 'home'
                            page.screenshot(path=str(OUT/f'{name}-{theme}-{width}.png'))
                            if path=='/':
                                page.screenshot(path=str(OUT/f'home-{theme}-{width}-full.png'),full_page=True)
                                for selector in ('.launch-interest','.ai-showcase','.client-outcome'):
                                    page.locator('.site-header').evaluate('e=>e.hidden=true')
                                    page.locator(selector).screenshot(path=str(OUT/f'{selector[1:]}-{theme}-{width}.png'))
                                    page.locator('.site-header').evaluate('e=>e.hidden=false')
            # Saved preference wins over a system change, and navigation preserves it.
            page.set_viewport_size({'width':1440,'height':1000})
            page.goto(origin+'/',wait_until='networkidle')
            page.locator('[data-theme-toggle]').click()
            assert page.locator('html').get_attribute('data-theme')=='dark'
            page.emulate_media(color_scheme='light')
            page.reload(wait_until='networkidle')
            assert page.locator('html').get_attribute('data-theme')=='dark'
            # Scroll visibly selects six different evidence panes; manual jumps also work.
            for key in ('endpoint','validate','capture','analyze','document','deliver'):
                scene=page.locator(f'#story-{key}')
                scene.evaluate("e=>scrollTo({top:scrollY+e.getBoundingClientRect().top+e.offsetHeight/2-innerHeight*.45,behavior:'instant'})")
                page.wait_for_function('(key)=>document.querySelector("[data-evidence-story]").dataset.activeScene===key',arg=key)
                assert page.locator(f'[data-preview={key}]').is_visible()
                assert page.locator(f'[data-stage-link={key}]').get_attribute('aria-current')=='step'
                page.wait_for_timeout(450)  # allow the deliberate 400 ms pane transition to settle
                page.locator('.story-viewer').screenshot(path=str(OUT/f'story-{key}.png'))
            page.locator('[data-stage-link=analyze]').click()
            page.wait_for_function('() => document.querySelector("[data-evidence-story]").dataset.activeScene==="analyze"')
            page.emulate_media(reduced_motion='reduce')
            assert page.locator('[data-preview=analyze]').evaluate('e=>getComputedStyle(e).animationName')=='none'
            # Keyboard tabs and real-report magnification.
            page.goto(origin+'/',wait_until='networkidle')
            page.get_by_role('tab',name='Validate').focus();page.keyboard.press('ArrowRight')
            assert page.locator('#panel-capture').is_visible()
            page.keyboard.press('End');assert page.locator('#panel-document').is_visible()
            page.goto(origin+'/reports',wait_until='networkidle')
            opener=page.locator('[data-report-page]').first;opener.click()
            assert page.locator('dialog').is_visible()
            page.locator('[data-report-zoom]').click()
            assert page.locator('dialog').evaluate('e=>e.classList.contains("is-zoomed")')
            page.locator('.lightbox-content').focus();page.keyboard.press('ArrowDown')
            page.locator('[data-report-zoom]').click()
            page.screenshot(path=str(OUT/'report-lightbox.png'))
            page.keyboard.press('Escape')
            assert opener.evaluate('e=>e===document.activeElement')
            # Five expanding cards: fixed widths, every artwork, both themes and phone fallback.
            page.emulate_media(reduced_motion='no-preference')
            for theme in ('dark','light'):
                page.evaluate('(theme)=>localStorage.setItem("vrioscu-theme",theme)',theme)
                for width in (1440,1024,768,640,390,320):
                    page.mouse.move(0,0)
                    page.set_viewport_size({'width':width,'height':1000})
                    page.goto(origin+'/',wait_until='networkidle')
                    rail=page.locator('[data-report-rail]')
                    cards=rail.locator('[data-report-card]')
                    buttons=rail.locator('[data-report-select]')
                    assert cards.count()==5
                    assert cards.nth(0).evaluate('e=>e.classList.contains("is-active")')
                    rail.scroll_into_view_if_needed()
                    rail.locator('img').evaluate_all('imgs=>imgs.forEach(i=>i.loading="eager")')
                    page.wait_for_function('() => Array.from(document.querySelectorAll(".rail-art img")).every(i=>i.complete&&i.naturalWidth)')
                    for index in range(5):
                        if width>640:buttons.nth(index).hover()
                        else:buttons.nth(index).click()
                        page.wait_for_timeout(700)
                        assert cards.locator('.rail-caption[aria-hidden=false]').count()==1
                        assert buttons.nth(index).get_attribute('aria-expanded')=='true',(theme,width,index)
                        assert rail.locator('[data-report-page][tabindex="0"]').count()==1
                        bounds=rail.evaluate('e=>{const b=e.getBoundingClientRect();return Array.from(e.children).every(c=>c.getBoundingClientRect().right<=b.right+1)}')
                        assert bounds,(theme,width,index)
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(theme,width,index)
                    # Keyboard focus and arrow keys select cards without opening a viewer.
                    buttons.nth(0).focus();page.keyboard.press('ArrowRight')
                    assert buttons.nth(1).get_attribute('aria-expanded')=='true'
                    page.keyboard.press('End');assert buttons.nth(4).get_attribute('aria-expanded')=='true'
                    buttons.nth(3).focus();page.wait_for_timeout(700)
                    assert cards.nth(3).locator('img').get_attribute('src').split('?')[0].endswith('/ai.webp')
                    if width in (1440,390):
                        page.locator('.site-header').evaluate('e=>e.hidden=true')
                        rail.screenshot(path=str(OUT/f'report-rail-{theme}-{width}.png'))
                        page.locator('.site-header').evaluate('e=>e.hidden=false')
                    rail_checks.append({'width':width,'theme':theme,'cards':5})
            # A tap expands without navigation; a second explicit Explore action opens the real page.
            touch=browser.new_context(has_touch=True,viewport={'width':390,'height':844})
            touch.route('**/*',lambda route:route.continue_() if route.request.url.startswith(origin+'/') else route.abort())
            mobile=touch.new_page();mobile.on('pageerror',lambda e:errors.append(str(e)))
            mobile.goto(origin+'/',wait_until='networkidle')
            mobile.locator('[data-report-select]').nth(3).tap()
            assert mobile.locator('[data-report-select]').nth(3).get_attribute('aria-expanded')=='true'
            assert not mobile.locator('dialog').is_visible()
            explore=mobile.locator('.report-rail-card--ai [data-report-page]')
            explore.tap();assert mobile.locator('dialog').is_visible()
            assert 'AI Validation Insights' in mobile.locator('#report-dialog-title').inner_text()
            mobile.wait_for_function('() => document.querySelector("[data-lightbox-image]").naturalWidth===1800')
            mobile.screenshot(path=str(OUT/'rail-touch-lightbox.png'))
            mobile.keyboard.press('Escape');assert explore.evaluate('e=>e===document.activeElement')
            mobile.emulate_media(reduced_motion='reduce')
            mobile.locator('[data-report-select]').nth(1).tap()
            assert float(mobile.locator('[data-report-card]').nth(1).evaluate('e=>parseFloat(getComputedStyle(e).transitionDuration)'))<.01
            assert mobile.locator('.is-active .rail-caption').evaluate('e=>getComputedStyle(e).transitionDelay')=='0s'
            touch.close()
            # Browser form submission saves interest and gives truthful feedback.
            page.goto(origin+'/',wait_until='networkidle')
            page.locator('#launch-first').fill('Browser');page.locator('#launch-last').fill('Check')
            page.locator('#launch-email').fill('browser-check@example.com')
            page.locator('.launch-form input[name=consent]').check()
            page.locator('.launch-form button[type=submit]').click()
            page.wait_for_url('**/launch-interest/saved')
            assert 'No email has been sent' in page.locator('main').inner_text()
            # Admin sign-in uses the actual browser flow, in a disposable database.
            page.goto(origin+'/login')
            page.locator('[name=identifier]').fill('preview_admin');page.locator('[name=password]').fill(PASSWORD)
            page.locator('main button[type=submit]').click();page.wait_for_url('**/admin')
            page.emulate_media(reduced_motion='no-preference')
            for theme in ('dark','light'):
                page.evaluate('(theme)=>{localStorage.setItem("vrioscu-theme",theme);document.documentElement.dataset.theme=theme}',theme)
                for width in (1440,390,320):
                    page.set_viewport_size({'width':width,'height':1000})
                    for path in (('/admin/releases','/admin/releases/new') if args.targeted else ADMIN):
                        response=page.goto(origin+path,wait_until='networkidle')
                        assert response.status==200,(path,response.status)
                        check_layout(page,path,width,theme);checks.append({'path':path,'width':width,'theme':theme})
                        if width in (1440,390) and path in ('/admin','/admin/analytics','/admin/launch-interest','/admin/releases/new'):
                            page.evaluate("scrollTo({top:0,behavior:'instant'})")
                            page.screenshot(path=str(OUT/f'{path.strip("/").replace("/","-")}-{theme}-{width}.png'))
            page.set_viewport_size({'width':1440,'height':1000})
            page.goto(origin+'/admin/analytics');page.locator('#days').select_option('30');page.get_by_role('button',name='Apply').click()
            assert '30 days' in page.locator('#days').inner_text()
            assert 'IST' in page.locator('main').inner_text()
            page.goto(origin+'/admin/launch-interest')
            page.locator('input[name=visible]').uncheck();page.get_by_role('button',name='Save settings').click()
            page.goto(origin+'/');assert page.locator('#launch-interest').count()==0
            page.goto(origin+'/admin/launch-interest');page.locator('input[name=visible]').check();page.locator('input[name=registrations_enabled]').uncheck();page.get_by_role('button',name='Save settings').click()
            page.goto(origin+'/');assert 'Registrations are paused' in page.locator('main').inner_text()
            # Publish/unpublish/delete via admin forms. Assert redirects without fetching the installer.
            page.goto(origin+'/admin/releases/new')
            assert page.locator('[name=sha256]').count()==0
            for field,value in case.release_payload(version='2.4.1').items():
                if field=='sha256':continue
                locator=page.locator(f'[name={field}]')
                if field=='is_published':locator.check()
                elif field=='channel':locator.select_option(value)
                else:locator.fill(str(value))
            page.get_by_role('button',name='Add release',exact=True).click();page.wait_for_url('**/admin/releases')
            edit=page.locator('main .table-wrap a[href^="/admin/releases/"]').first.get_attribute('href')
            page.goto(origin+'/download');assert 'Version 2.4.1' in page.locator('main').inner_text()
            assert 'SHA-256' not in page.locator('main').inner_text()
            assert page.locator('[data-copy]').count()==0
            response=context.request.get(origin+'/download/latest',max_redirects=0)
            assert response.status==302 and response.headers['location'].startswith('https://downloads.example.com/')
            page.goto(origin+edit);page.locator('[name=is_published]').uncheck();page.get_by_role('button',name='Save release',exact=True).click()
            page.goto(origin+'/download');assert 'Coming Soon' in page.locator('main').inner_text()
            page.goto(origin+edit);page.locator('[name=is_published]').check();page.get_by_role('button',name='Save release',exact=True).click()
            page.goto(origin+'/admin/releases');page.once('dialog',lambda dialog:dialog.accept());page.get_by_role('button',name='Delete').click()
            page.goto(origin+'/download');assert 'Coming Soon' in page.locator('main').inner_text()
            # Small-screen navigation and no-JS fallback.
            page.set_viewport_size({'width':390,'height':844});page.goto(origin+'/')
            toggle=page.get_by_role('button',name='Menu');toggle.click();assert toggle.get_attribute('aria-expanded')=='true'
            page.keyboard.press('Escape');assert toggle.get_attribute('aria-expanded')=='false'
            nojs=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':844})
            fallback=nojs.new_page();fallback.goto(origin+'/')
            assert fallback.locator('#site-nav').is_visible()
            assert fallback.locator('.story-mobile-media').first.is_visible()
            assert fallback.locator('.rail-explore').count()==5
            assert all(fallback.locator('.rail-explore').nth(i).is_visible() for i in range(5))
            nojs.close();browser.close()
        assert not errors,errors
        assert not failed,failed
        report={'checks':checks,'rail_checks':rail_checks,'console_errors':errors,'failed_responses':failed,'interactions':'passed',
                'database':'isolated disposable fixture','installer':'redirect inspected; external asset not fetched'}
        (OUT/'experience-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(f'PASS: {len(checks)} public/admin viewport-theme checks; {len(rail_checks)} five-card rail checks; consent, scroll story, themes, launch controls, releases without a checksum, keyboard, touch, reduced motion and no-JS fallback. No console errors or failed responses.')
    finally:
        server.shutdown();thread.join(timeout=5);case.tearDown()


if __name__=='__main__':
    main()
