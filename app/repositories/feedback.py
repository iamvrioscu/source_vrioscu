from ..time_utils import now_iso
from .base import rows

STATUSES = ("new", "reviewed", "closed")


class FeedbackRepository:
    def __init__(self, conn):
        self.conn = conn

    def create(self, *, user_id, category, app_version, message):
        return self.conn.execute(
            "INSERT INTO feedback (user_id, category, app_version, message, created_at) VALUES (?,?,?,?,?)",
            (user_id, category, app_version, message, now_iso())).lastrowid

    def list(self, *, status=None, limit=50, offset=0):
        sql = ("SELECT f.id, f.category, f.app_version, f.message, f.status, f.created_at,"
               " u.username FROM feedback f JOIN users u ON u.id = f.user_id")
        params = []
        if status in STATUSES:
            sql += " WHERE f.status = ?"; params.append(status)
        sql += " ORDER BY f.created_at DESC, f.id DESC LIMIT ? OFFSET ?"
        return rows(self.conn.execute(sql, params + [limit, offset]))

    def for_user(self, user_id):
        return rows(self.conn.execute(
            "SELECT id, category, app_version, message, status, created_at FROM feedback"
            " WHERE user_id = ? ORDER BY created_at DESC, id DESC", (user_id,)))

    def count(self, status=None):
        if status in STATUSES:
            return self.conn.execute("SELECT COUNT(*) FROM feedback WHERE status = ?", (status,)).fetchone()[0]
        return self.conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]

    def set_status(self, feedback_id, status):
        if status not in STATUSES:
            raise ValueError("invalid status")
        return self.conn.execute("UPDATE feedback SET status = ? WHERE id = ?", (status, feedback_id)).rowcount
