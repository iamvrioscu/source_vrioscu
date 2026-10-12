import json

from ..time_utils import now_iso
from .base import rows

STATUSES = ("new", "reviewed", "closed")
TYPES = ("feedback", "bug_report", "problem_report", "feature_request")


class DesktopSubmissionRepository:
    def __init__(self, conn):
        self.conn = conn

    def create(
        self, *, user_id, client_submission_id, submission_type, details,
        metadata, app_version="", client_created_at=""
    ):
        details_json = json.dumps(details, ensure_ascii=False, separators=(",", ":"))
        metadata_json = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
        cursor = self.conn.execute(
            """
            INSERT INTO desktop_submissions (
                user_id, client_submission_id, submission_type, details_json,
                metadata_json, app_version, client_created_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, client_submission_id) DO NOTHING
            """,
            (
                user_id, client_submission_id, submission_type, details_json,
                metadata_json, app_version, client_created_at, now_iso(),
            ),
        )
        created = cursor.rowcount == 1
        row = self.conn.execute(
            """
            SELECT id, client_submission_id, submission_type, status, created_at
            FROM desktop_submissions
            WHERE user_id = ? AND client_submission_id = ?
            """,
            (user_id, client_submission_id),
        ).fetchone()
        result = dict(row) if row else None
        if result:
            result["duplicate"] = not created
        return result

    def list(self, *, status=None, limit=50, offset=0):
        sql = """
            SELECT s.id, s.user_id, s.client_submission_id, s.submission_type,
                   s.details_json, s.metadata_json, s.app_version,
                   s.client_created_at, s.status, s.created_at,
                   u.username, u.email
            FROM desktop_submissions s
            JOIN users u ON u.id = s.user_id
        """
        params = []
        if status in STATUSES:
            sql += " WHERE s.status = ?"
            params.append(status)
        sql += " ORDER BY s.created_at DESC, s.id DESC LIMIT ? OFFSET ?"
        items = rows(self.conn.execute(sql, params + [limit, offset]))
        for item in items:
            item["details"] = json.loads(item.pop("details_json"))
            item["metadata"] = json.loads(item.pop("metadata_json"))
        return items

    def count(self, status=None):
        if status in STATUSES:
            return self.conn.execute(
                "SELECT COUNT(*) FROM desktop_submissions WHERE status = ?",
                (status,),
            ).fetchone()[0]
        return self.conn.execute(
            "SELECT COUNT(*) FROM desktop_submissions"
        ).fetchone()[0]

    def set_status(self, submission_id, status):
        if status not in STATUSES:
            raise ValueError("invalid status")
        return self.conn.execute(
            "UPDATE desktop_submissions SET status = ? WHERE id = ?",
            (status, submission_id),
        ).rowcount
