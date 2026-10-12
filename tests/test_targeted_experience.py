"""Consent entry points and the checksum migration's existing-data contract."""
from pathlib import Path
import shutil
from unittest.mock import patch

from app.db import MIGRATIONS_DIR, connect, migrate, transaction
from app.repositories import Repositories
from tests.helpers import AppTestCase, SHA


class TargetedExperienceTests(AppTestCase):
    def test_privacy_controls_are_discreet_and_popup_markup_is_removed(self):
        for path in ('/', '/reports', '/product', '/download', '/privacy'):
            html = self.client.get(path).get_data(as_text=True)
            self.assertNotIn('data-consent-banner', html)
            self.assertNotIn('data-cookie-choices', html)
            self.assertIn('href="/privacy#analytics-privacy"', html)
            if path != '/privacy':
                self.assertNotIn('action="/privacy/analytics"', html)
        privacy = self.client.get('/privacy').get_data(as_text=True)
        self.assertIn('Decline / withdraw analytics', privacy)
        self.assertIn('Not set (optional analytics is off)', privacy)
        self.assertIsNone(self.client.get_cookie('vr_analytics'))

    def test_checksum_migration_preserves_releases_and_download_counts(self):
        old_dir = Path(self.tmp) / 'old-migrations'
        old_dir.mkdir()
        for source in MIGRATIONS_DIR.glob('*.sql'):
            if source.name < '0005':
                shutil.copyfile(source,old_dir / source.name)
        legacy = Path(self.tmp) / 'legacy.db'
        with patch('app.db.MIGRATIONS_DIR',old_dir):
            migrate(legacy)
        conn = connect(legacy)
        repos = Repositories(conn)
        with transaction(conn):
            uid = repos.users.create(username='owner',email='owner@example.com',password_hash='existing-hash')
            # Seed the historical schema with its original column list.
            payload = {**self.release_payload(), 'is_mandatory':0,'is_signed':0,
                       'created_by':uid,'created_at':'2026-10-01T00:00:00Z','updated_at':'2026-10-01T00:00:00Z'}
            rid = conn.execute('INSERT INTO releases('+','.join(payload)+') VALUES('+','.join('?' for _ in payload)+')',tuple(payload.values())).lastrowid
            repos.releases.record_download(rid)
            repos.releases.record_download(rid)
        before = repos.releases.get(rid)
        stats = list(map(tuple,conn.execute('SELECT * FROM download_stats')))
        conn.close()
        self.assertEqual(migrate(legacy),['0005_optional_release_checksum','0006_installer_storage'])
        self.assertEqual(migrate(legacy),[], 'migration is not reapplied')
        conn = connect(legacy)
        repos = Repositories(conn)
        self.assertEqual(repos.releases.get(rid),{**before,'storage_key':None,'uploaded_at':None})
        self.assertEqual(repos.releases.get(rid)['sha256'],SHA)
        self.assertEqual(list(map(tuple,conn.execute('SELECT * FROM download_stats'))),stats)
        self.assertEqual(list(conn.execute('PRAGMA foreign_key_check')),[])
        self.assertEqual(conn.execute('PRAGMA foreign_keys').fetchone()[0],1)
        with transaction(conn):
            other = repos.releases.create({**self.release_payload(version='1.0.1'),'sha256':None,'is_mandatory':0,'is_signed':0})
            repos.releases.record_download(other)
            repos.releases.delete(other)
        self.assertEqual(repos.releases.download_totals(),{rid:2}, 'cascade still works after migration')
        conn.close()
