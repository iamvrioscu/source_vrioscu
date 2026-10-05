from ..time_utils import now_iso
from .base import row


class SessionRepository:
    def __init__(self, conn):
        self.conn = conn

    def create(self, *, token_hash, user_id, csrf_secret, expires_at):
        ts = now_iso()
        self.conn.execute(
            "INSERT INTO sessions (token_hash, user_id, csrf_secret, created_at, last_seen_at, expires_at)"
            " VALUES (?,?,?,?,?,?)", (token_hash, user_id, csrf_secret, ts, ts, expires_at))

    def get_active(self, token_hash):
        return row(self.conn.execute(
            "SELECT s.*, u.username, u.email, u.role, u.is_active, u.first_name, u.last_name"
            " FROM sessions s JOIN users u ON u.id = s.user_id"
            " WHERE s.token_hash = ? AND s.revoked_at IS NULL AND s.expires_at > ?",
            (token_hash, now_iso())).fetchone())

    def touch(self, session_id):
        self.conn.execute("UPDATE sessions SET last_seen_at = ? WHERE id = ?", (now_iso(), session_id))

    def revoke(self, session_id):
        self.conn.execute("UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                          (now_iso(), session_id))

    def revoke_all_for_user(self, user_id, except_id=None):
        sql, params = "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL", [now_iso(), user_id]
        if except_id:
            sql += " AND id != ?"; params.append(except_id)
        self.conn.execute(sql, params)

    def purge_expired(self):
        self.conn.execute("DELETE FROM sessions WHERE expires_at < ? OR revoked_at IS NOT NULL", (now_iso(),))

    def count_active(self):
        return self.conn.execute("SELECT COUNT(*) FROM sessions WHERE revoked_at IS NULL AND expires_at > ?",
                                 (now_iso(),)).fetchone()[0]
