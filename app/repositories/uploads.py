from .base import row, rows
from ..time_utils import now_iso


class UploadRepository:
    def __init__(self, conn):
        self.conn = conn

    def get(self, upload_id):
        return row(self.conn.execute('SELECT * FROM release_uploads WHERE id=?', (upload_id,)).fetchone())

    def create(self, upload_id, owner, filename, size, expires):
        ts = now_iso()
        self.conn.execute('INSERT INTO release_uploads(id,owner_id,original_filename,expected_bytes,created_at,updated_at,expires_at) VALUES(?,?,?,?,?,?,?)',
                          (upload_id, owner, filename, size, ts, ts, expires))

    def reservations(self):
        return self.conn.execute("SELECT COALESCE(SUM(expected_bytes-received_bytes),0) FROM release_uploads WHERE state='uploading'").fetchone()[0]

    def active_count(self, owner):
        return self.conn.execute("SELECT COUNT(*) FROM release_uploads WHERE owner_id=? AND state IN ('uploading','verified')", (owner,)).fetchone()[0]

    def progress(self, upload_id, received):
        self.conn.execute('UPDATE release_uploads SET received_bytes=?,updated_at=? WHERE id=?', (received, now_iso(), upload_id))

    def verified(self, upload_id, key, digest):
        self.conn.execute("UPDATE release_uploads SET state='verified',storage_key=?,sha256=?,updated_at=? WHERE id=?", (key, digest, now_iso(), upload_id))

    def attach(self, upload_id, release_id):
        self.conn.execute("UPDATE release_uploads SET state='attached',release_id=?,updated_at=? WHERE id=?", (release_id, now_iso(), upload_id))

    def cancel(self, upload_id):
        self.conn.execute("UPDATE release_uploads SET state='cancelled',updated_at=? WHERE id=?", (now_iso(), upload_id))

    def expired(self):
        return rows(self.conn.execute("SELECT * FROM release_uploads WHERE state IN ('uploading','verified') AND expires_at < ?", (now_iso(),)))

    def referenced(self, key):
        return self.conn.execute('SELECT 1 FROM releases WHERE storage_key=?', (key,)).fetchone() is not None
