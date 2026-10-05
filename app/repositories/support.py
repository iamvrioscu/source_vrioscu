from ..time_utils import now_iso
from .base import rows

STATUSES = ("new", "in_progress", "closed")


class SupportRepository:
    def __init__(self, conn):
        self.conn = conn

    def create(self, *, user_id, name, email, topic, message):
        return self.conn.execute(
            "INSERT INTO support_requests (user_id, name, email, topic, message, created_at)"
            " VALUES (?,?,?,?,?,?)", (user_id, name, email, topic, message, now_iso())).lastrowid

    def list(self, *, status=None, limit=50, offset=0):
        sql = "SELECT id, name, email, topic, message, status, created_at FROM support_requests"
        params = []
        if status in STATUSES:
            sql += " WHERE status = ?"; params.append(status)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
        return rows(self.conn.execute(sql, params + [limit, offset]))

    def for_user(self, user_id):
        return rows(self.conn.execute(
            "SELECT id, topic, message, status, created_at FROM support_requests"
            " WHERE user_id = ? ORDER BY created_at DESC, id DESC", (user_id,)))

    def count(self, status=None):
        if status in STATUSES:
            return self.conn.execute("SELECT COUNT(*) FROM support_requests WHERE status = ?",
                                     (status,)).fetchone()[0]
        return self.conn.execute("SELECT COUNT(*) FROM support_requests").fetchone()[0]

    def set_status(self, request_id, status):
        if status not in STATUSES:
            raise ValueError("invalid status")
        return self.conn.execute("UPDATE support_requests SET status = ? WHERE id = ?",
                                 (status, request_id)).rowcount
