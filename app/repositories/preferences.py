from ..time_utils import now_iso
from .base import rows


class PreferenceRepository:
    def __init__(self, conn):
        self.conn = conn

    def get_updates(self, user_id) -> bool:
        r = self.conn.execute("SELECT opted_in FROM product_update_preferences WHERE user_id = ?",
                              (user_id,)).fetchone()
        return bool(r and r[0])

    def set_updates(self, user_id, opted_in: bool, notice_version: str):
        self.conn.execute(
            "INSERT INTO product_update_preferences (user_id, opted_in, updated_at) VALUES (?,?,?)"
            " ON CONFLICT(user_id) DO UPDATE SET opted_in = excluded.opted_in, updated_at = excluded.updated_at",
            (user_id, 1 if opted_in else 0, now_iso()))
        self.record_consent(user_id, "product_updates", opted_in, notice_version)

    def record_consent(self, user_id, purpose, granted: bool, notice_version):
        self.conn.execute(
            "INSERT INTO consent_records (user_id, purpose, granted, notice_version, recorded_at)"
            " VALUES (?,?,?,?,?)", (user_id, purpose, 1 if granted else 0, notice_version, now_iso()))

    def consent_history(self, user_id):
        return rows(self.conn.execute(
            "SELECT purpose, granted, notice_version, recorded_at FROM consent_records"
            " WHERE user_id = ? ORDER BY recorded_at, id", (user_id,)))

    def subscribers(self):
        return rows(self.conn.execute(
            "SELECT u.id, u.username, u.email, u.first_name, u.last_name, p.updated_at AS opted_in_at"
            " FROM product_update_preferences p JOIN users u ON u.id = p.user_id"
            " WHERE p.opted_in = 1 AND u.is_active = 1 ORDER BY p.updated_at DESC"))

    def count_subscribers(self):
        return self.conn.execute(
            "SELECT COUNT(*) FROM product_update_preferences p JOIN users u ON u.id = p.user_id"
            " WHERE p.opted_in = 1 AND u.is_active = 1").fetchone()[0]
