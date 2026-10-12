from datetime import datetime, timedelta, timezone, date
from unittest.mock import patch
import sqlite3
import io
from openpyxl import load_workbook

from app import create_app
from app.db import transaction
from app.time_utils import display_ist, ist_day_bounds, parse_iso
from tests.helpers import AppTestCase


class LaunchInterestTests(AppTestCase):
    def submit(self, **changes):
        return self.client.post('/launch-interest',data={'first_name':' Ada ','last_name':' Lovelace ',
            'email':' ADA@EXAMPLE.COM ','consent':'1','csrf_token':self.csrf(),**changes})

    def settings_payload(self, **changes):
        conn,repos = self.repos()
        data = repos.launch.settings(); conn.close()
        data.update(changes)
        return data

    def test_registration_normalizes_and_duplicate_preserves_original(self):
        self.assertEqual(self.submit().status_code,303)
        self.assertEqual(self.submit(first_name='Changed').status_code,303)
        conn,repos = self.repos()
        self.assertEqual(repos.launch.count(),1)
        record = repos.launch.list()[0]
        self.assertEqual((record['first_name'],record['last_name'],record['email']),('Ada','Lovelace','ada@example.com'))
        self.assertEqual(record['status'],'registered')
        self.assertEqual(record['consent_granted'],1)
        self.assertIsNone(record['confirmed_at'])
        self.assertTrue(record['registered_at'].endswith('Z'))
        conn.close()

    def test_invalid_and_missing_consent_not_saved(self):
        for change in ({'email':'invalid'},{'first_name':''},{'last_name':'<script>'},{'consent':''}):
            self.assertEqual(self.submit(**change).status_code,422,change)
        conn,repos=self.repos(); self.assertEqual(repos.launch.count(),0);conn.close()

    def test_visibility_and_registration_are_independent_and_persist(self):
        admin=self.make_admin()
        data=self.settings_payload(visible='',registrations_enabled='1',heading='A new launch heading')
        data['csrf_token']=self.csrf(admin)
        self.assertEqual(admin.post('/admin/launch-interest/settings',data=data).status_code,303)
        self.assertNotIn('id="launch-interest"',self.client.get('/').get_data(as_text=True))
        self.assertEqual(self.submit().status_code,303,'Hidden section must not imply closed registrations')
        # A new factory applies migrations without overwriting persisted settings or records.
        second=create_app({'env':'test','database_path':self.db_path,'base_url':self.base_url,'secret_key':'t'*48})
        self.assertNotIn('id="launch-interest"',second.test_client().get('/').get_data(as_text=True))
        data=self.settings_payload(visible='1',registrations_enabled='')
        data['csrf_token']=self.csrf(admin)
        self.assertEqual(admin.post('/admin/launch-interest/settings',data=data).status_code,303)
        self.assertIn('Registrations are paused',self.client.get('/').get_data(as_text=True))
        self.assertEqual(self.submit(email='other@example.com').status_code,403)
        self.assertIn('ada@example.com',admin.get('/admin/launch-interest').get_data(as_text=True))

    def test_admin_actions_search_filter_and_sort(self):
        self.submit()
        self.submit(first_name='Zed',email='zed@example.com')
        admin=self.make_admin()
        html=admin.get('/admin/launch-interest?q=ada&sort=email').get_data(as_text=True)
        self.assertIn('ada@example.com',html);self.assertNotIn('zed@example.com',html)
        conn,repos=self.repos();rid=repos.launch.list(search='ada')[0]['id'];conn.close()
        token=self.csrf(admin)
        self.assertEqual(admin.post(f'/admin/launch-interest/{rid}/unsubscribe',data={'csrf_token':token}).status_code,303)
        self.submit()  # duplicate must not restore withdrawn consent
        conn,repos=self.repos();self.assertEqual(repos.launch.list(search='ada')[0]['consent_granted'],0);conn.close()
        self.assertIn('ada@example.com',admin.get('/admin/launch-interest?status=unsubscribed').get_data(as_text=True))
        self.assertEqual(admin.post(f'/admin/launch-interest/{rid}/delete',data={'csrf_token':token}).status_code,303)
        conn,repos=self.repos();self.assertEqual(repos.launch.count(),1)
        self.assertIn('launch.unsubscribe',[r['action'] for r in repos.audit.recent()]);conn.close()

    def test_pagination_and_wildcard_search(self):
        conn,repos=self.repos()
        with transaction(conn):
            for i in range(53):
                repos.launch.register({'first_name':f'Person{i}','last_name':'Test','email':f'p{i}@example.com'},'1')
        self.assertEqual(repos.launch.count('%'),0)
        conn.close()
        admin=self.make_admin()
        html=admin.get('/admin/launch-interest?page=2').get_data(as_text=True)
        self.assertIn('Page 2 of 2',html)
        self.assertEqual(html.count('email unverified'),3)

    def test_authorization_csrf_and_server_rate_limit(self):
        self.assertEqual(self.client.get('/admin/launch-interest').status_code,302)
        self.assertEqual(self.client.post('/launch-interest',data={}).status_code,400)
        self.register();self.login()
        self.assertEqual(self.client.get('/admin/launch-interest').status_code,403)
        self.assertEqual(self.client.post('/admin/launch-interest/settings',data={'csrf_token':self.csrf()}).status_code,403)
        admin=self.make_admin()
        self.assertEqual(admin.post('/admin/launch-interest/settings',data={}).status_code,400)
        for i in range(5):self.assertEqual(self.submit(email=f'new{i}@example.com').status_code,303)
        self.assertEqual(self.submit(email='limit@example.com').status_code,429)

    def test_failed_database_write_does_not_report_success(self):
        with patch('app.repositories.launch.LaunchRepository.register',side_effect=sqlite3.OperationalError('test failure')):
            response=self.submit()
        self.assertEqual(response.status_code,503)
        self.assertIn('couldn’t save',response.get_data(as_text=True))
        conn,repos=self.repos();self.assertEqual(repos.launch.count(),0);conn.close()

    def test_launch_export_is_protected_and_neutralizes_formulas(self):
        self.submit(first_name='=SUM(1,2)')
        self.assertEqual(self.client.post('/admin/exports/launch_interest',data={'csrf_token':self.csrf()}).status_code,302)
        admin=self.make_admin()
        response=admin.post('/admin/exports/launch_interest',data={'csrf_token':self.csrf(admin)})
        self.assertEqual(response.status_code,200)
        workbook=load_workbook(io.BytesIO(response.data))
        sheet=workbook.active
        self.assertEqual(sheet['A2'].value,"'=SUM(1,2)")
        self.assertNotEqual(sheet['A2'].data_type,'f')
        self.assertIn('IST',sheet['F2'].value)


class AnalyticsTests(AppTestCase):
    def consent(self, choice='allow', **headers):
        return self.client.post('/privacy/analytics',data={'choice':choice,'csrf_token':self.csrf()},headers=headers)

    def event(self,event_id='a'*32,kind='view',path='/',**headers):
        return self.client.post('/analytics/event',json={'path':path,'event_id':event_id,'kind':kind,
            'referrer':'https://referrer.example/path?secret=discard'},headers={'X-CSRF-Token':self.csrf(),**headers})

    def test_opt_in_required_and_decline_forgets_browser(self):
        self.assertEqual(self.event().status_code,204)
        conn,repos=self.repos();self.assertEqual(repos.analytics.dashboard()['metrics']['views'],0);conn.close()
        self.assertEqual(self.consent().status_code,303)
        self.assertTrue(self.client.get_cookie('vr_visitor').http_only)
        self.assertEqual(self.event().status_code,204)
        conn,repos=self.repos();self.assertEqual(repos.analytics.dashboard()['metrics']['views'],1);conn.close()
        self.consent('decline')
        self.assertIsNone(self.client.get_cookie('vr_visitor'))
        conn,repos=self.repos();self.assertEqual(repos.analytics.dashboard()['metrics']['views'],0);conn.close()

    def test_duplicate_events_and_heartbeat_do_not_inflate_views(self):
        self.consent();self.event();self.event();self.event(kind='heartbeat')
        conn,repos=self.repos();stats=repos.analytics.dashboard()['metrics']
        self.assertEqual((stats['views'],stats['visits'],stats['unique'],stats['active']),(1,1,1,1))
        rec=conn.execute('SELECT * FROM analytics_visits').fetchone()
        self.assertEqual(rec['referrer'],'referrer.example')
        fields=set(rec.keys())
        self.assertFalse(fields & {'ip','ip_address','user_id','user_agent'})
        conn.close()

    def test_do_not_track_global_privacy_and_signed_in_excluded(self):
        self.consent(DNT='1');self.assertEqual(self.client.get_cookie('vr_analytics').value,'decline')
        self.consent();self.event(DNT='1');self.event(**{'Sec-GPC':'1'})
        self.register();self.login();self.event(event_id='b'*32)
        conn,repos=self.repos();self.assertEqual(repos.analytics.dashboard()['metrics']['views'],0);conn.close()

    def test_private_paths_invalid_shapes_and_csrf_rejected(self):
        self.consent()
        for path in ['/admin','/account','/login','/reports?email=private@example.com']:
            self.assertEqual(self.event(path=path).status_code,400)
        self.assertEqual(self.client.post('/analytics/event',json=[] ,headers={'X-CSRF-Token':self.csrf()}).status_code,400)
        self.assertEqual(self.client.post('/analytics/event',json={'path':[],'event_id':'a'*32},headers={'X-CSRF-Token':self.csrf()}).status_code,400)
        self.assertEqual(self.client.post('/analytics/event',json={}).status_code,400)
        self.assertEqual(self.client.get('/admin/analytics').status_code,302)
        self.register();self.login();self.assertEqual(self.client.get('/admin/analytics').status_code,403)

    def test_activity_window_session_boundary_and_retention(self):
        conn,repos=self.repos()
        now=datetime(2026,10,12,12,tzinfo=timezone.utc)
        with transaction(conn):
            repos.analytics.record('recent','1'*32,'/','Direct','Chrome','Desktop',now=now-timedelta(minutes=4))
            repos.analytics.record('idle','2'*32,'/product','Direct','Chrome','Mobile',now=now-timedelta(minutes=6))
        self.assertEqual(repos.analytics.dashboard(now=now)['metrics']['active'],1)
        with transaction(conn):
            repos.analytics.record('recent','3'*32,'/reports','Direct','Chrome','Desktop',now=now+timedelta(minutes=27))
        self.assertEqual(repos.analytics.dashboard(now=now+timedelta(minutes=27))['metrics']['visits'],3)
        with transaction(conn):
            repos.analytics.record('old','4'*32,'/','Direct','Other','Desktop',now=now-timedelta(days=91))
            repos.analytics.purge(now=now)
        self.assertIsNone(conn.execute("SELECT * FROM analytics_visitors WHERE id='old'").fetchone())
        conn.close()

    def test_ist_calendar_boundaries_for_counts_and_chart(self):
        conn,repos=self.repos()
        boundary=datetime(2026,10,12,18,30,tzinfo=timezone.utc)
        with transaction(conn):
            repos.analytics.record('yesterday','a'*32,'/','Direct','Other','Desktop',now=boundary-timedelta(seconds=1))
            repos.analytics.record('today','b'*32,'/reports','Direct','Other','Desktop',now=boundary)
        data=repos.analytics.dashboard(days=1,now=boundary+timedelta(seconds=5))
        self.assertEqual(data['metrics']['views'],1)
        self.assertEqual(data['metrics']['visits_1'],1)
        self.assertEqual(data['metrics']['visits_7'],2)
        self.assertEqual(data['trend'],[{'day':'2026-10-13','views':1}])
        conn.close()

    def test_dashboard_empty_state_and_bounded_periods(self):
        admin=self.make_admin()
        response=admin.get('/admin/analytics?days=30')
        self.assertEqual(response.status_code,200)
        self.assertIn('No consented page views',response.get_data(as_text=True))
        for days in ('10000','-1','bad'):
            self.assertEqual(admin.get('/admin/analytics?days='+days).status_code,400)


class ISTTests(AppTestCase):
    def test_utc_offsets_naive_history_and_midnight(self):
        self.assertEqual(display_ist('2026-10-12T10:10:25Z'),'12 Oct 2026, 03:40:25 PM IST')
        self.assertEqual(display_ist('2026-10-12T10:10:25'),'12 Oct 2026, 03:40:25 PM IST')
        self.assertEqual(display_ist('2026-10-13T00:00:00+05:30'),'13 Oct 2026, 12:00:00 AM IST')
        self.assertEqual(ist_day_bounds(date(2026,10,13)),('2026-10-12T18:30:00Z','2026-10-13T18:30:00Z'))
        self.assertEqual(parse_iso('2026-10-13T00:00:00+05:30').hour,18)
        self.assertEqual(display_ist('not-a-date'),'Invalid timestamp')
