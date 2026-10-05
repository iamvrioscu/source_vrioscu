import json

from ..time_utils import now_iso
from .base import rows


class AuditRepository:
    def __init__(self, conn):
        self.conn = conn

    def record(self, actor_user_id, action, target="", detail=None):
        self.conn.execute(
            "INSERT INTO audit_log (actor_user_id, action, target, detail, created_at) VALUES (?,?,?,?,?)",
            (actor_user_id, action, str(target), json.dumps(detail or {}, default=str), now_iso()))

    def recent(self, limit=25):
        return rows(self.conn.execute(
            "SELECT a.action, a.target, a.created_at, u.username AS actor FROM audit_log a"
            " LEFT JOIN users u ON u.id = a.actor_user_id ORDER BY a.id DESC LIMIT ?", (limit,)))
