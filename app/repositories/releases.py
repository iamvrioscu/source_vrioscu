from ..time_utils import now_iso, utcnow
from .base import row, rows

CHANNELS = ("PUBLIC_BETA", "STABLE", "INTERNAL", "DEV")
PUBLIC_CHANNELS = ("PUBLIC_BETA", "STABLE")
FIELDS = ("version", "channel", "release_date", "release_notes_url", "download_url",
          "installer_filename", "sha256", "file_size_bytes", "is_mandatory",
          "minimum_supported_version", "is_signed", "is_published")


class ReleaseRepository:
    def __init__(self, conn):
        self.conn = conn

    def create(self, data: dict, created_by=None):
        ts = now_iso()
        return self.conn.execute(
            f"INSERT INTO releases ({', '.join(FIELDS)}, created_by, created_at, updated_at)"
            f" VALUES ({', '.join('?' * len(FIELDS))}, ?, ?, ?)",
            (*[data[f] for f in FIELDS], created_by, ts, ts)).lastrowid

    def update(self, release_id, data: dict):
        fields = [f for f in FIELDS if f in data]  # fixed allowlist
        sets = ", ".join(f"{f} = ?" for f in fields)
        return self.conn.execute(f"UPDATE releases SET {sets}, updated_at = ? WHERE id = ?",
                                 (*[data[f] for f in fields], now_iso(), release_id)).rowcount

    def get(self, release_id):
        return row(self.conn.execute("SELECT * FROM releases WHERE id = ?", (release_id,)).fetchone())

    def exists(self, version, channel, exclude_id=None):
        sql, params = "SELECT 1 FROM releases WHERE version = ? AND channel = ?", [version, channel]
        if exclude_id:
            sql += " AND id != ?"; params.append(exclude_id)
        return self.conn.execute(sql, params).fetchone() is not None

    def delete(self, release_id):
        return self.conn.execute("DELETE FROM releases WHERE id = ?", (release_id,)).rowcount

    def list(self, channels=CHANNELS, published_only=False):
        marks = ",".join("?" * len(channels))
        sql = f"SELECT * FROM releases WHERE channel IN ({marks})"
        if published_only:
            sql += " AND is_published = 1"
        sql += " ORDER BY release_date DESC, id DESC"
        return rows(self.conn.execute(sql, list(channels)))

    def latest(self, channel):
        return row(self.conn.execute(
            "SELECT * FROM releases WHERE channel = ? AND is_published = 1"
            " ORDER BY release_date DESC, id DESC LIMIT 1", (channel,)).fetchone())

    def record_download(self, release_id):
        self.conn.execute(
            "INSERT INTO download_stats (release_id, day, count) VALUES (?, ?, 1)"
            " ON CONFLICT(release_id, day) DO UPDATE SET count = count + 1",
            (release_id, utcnow().strftime("%Y-%m-%d")))

    def download_totals(self):
        return {r[0]: r[1] for r in self.conn.execute(
            "SELECT release_id, SUM(count) FROM download_stats GROUP BY release_id")}
