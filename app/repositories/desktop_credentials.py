"""Database access for VRIOSCU desktop API credentials."""
from ..time_utils import now_iso
from .base import row


class DesktopCredentialRepository:
    def __init__(self, conn):
        self.conn = conn

    def create(self, *, user_id, token_hash):
        self.conn.execute(
            """
            INSERT INTO desktop_credentials
                (user_id, token_hash, created_at)
            VALUES (?, ?, ?)
            """,
            (user_id, token_hash, now_iso()),
        )

    def get_active(self, token_hash):
        return row(self.conn.execute(
            """
            SELECT dc.id, dc.user_id, dc.token_hash, dc.created_at,
                   dc.last_used_at, u.username, u.email, u.first_name,
                   u.last_name, u.country, u.purpose, u.role, u.is_active
            FROM desktop_credentials AS dc
            JOIN users AS u ON u.id = dc.user_id
            WHERE dc.token_hash = ?
              AND dc.revoked_at IS NULL
              AND u.is_active = 1
            """,
            (token_hash,),
        ).fetchone())

    def touch(self, credential_id):
        self.conn.execute(
            """
            UPDATE desktop_credentials
            SET last_used_at = ?
            WHERE id = ? AND revoked_at IS NULL
            """,
            (now_iso(), credential_id),
        )

    def revoke_for_user(self, user_id):
        self.conn.execute(
            """
            UPDATE desktop_credentials
            SET revoked_at = ?
            WHERE user_id = ? AND revoked_at IS NULL
            """,
            (now_iso(), user_id),
        )
