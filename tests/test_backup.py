import contextlib
import gzip
import io
import os
import sqlite3
from pathlib import Path

from scripts.backup_db import backup
from scripts.restore_db import restore
from tests.helpers import AppTestCase


class BackupRestoreTests(AppTestCase):
    def test_backup_and_restore_round_trip(self):
        self.register()
        db = Path(self.db_path)
        dest = Path(self.tmp) / "backups"
        archive = backup(db, dest, keep_days=14)
        self.assertTrue(archive.name.endswith(".db.gz"))
        self.assertEqual(os.stat(archive).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(dest).st_mode & 0o777, 0o700)
        with gzip.open(archive) as f:
            self.assertTrue(f.read(16).startswith(b"SQLite format 3"))

        # Damage the live data, then restore.
        conn = sqlite3.connect(db)
        conn.execute("DELETE FROM users")
        conn.commit()
        conn.close()
        with contextlib.redirect_stdout(io.StringIO()):
            previous = restore(archive, db, force=True)
        self.assertTrue(previous.exists())
        conn = sqlite3.connect(db)
        self.assertEqual(conn.execute("SELECT username FROM users").fetchone()[0], "alice")
        conn.close()
        self.assertEqual(os.stat(db).st_mode & 0o777, 0o600)

    def test_restore_rejects_corrupt_backup(self):
        bad = Path(self.tmp) / "bad.db.gz"
        with gzip.open(bad, "wb") as f:
            f.write(b"not a database" * 100)
        with self.assertRaises(Exception):
            restore(bad, Path(self.tmp) / "target.db", force=True)
        self.assertFalse((Path(self.tmp) / "target.db").exists())

    def test_retention_removes_old_backups(self):
        dest = Path(self.tmp) / "backups"
        dest.mkdir()
        old = dest / "vrioscu-20000101T000000Z.db.gz"
        old.write_bytes(b"x")
        os.utime(old, (0, 0))
        backup(Path(self.db_path), dest, keep_days=14)
        self.assertFalse(old.exists())
