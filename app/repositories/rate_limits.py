class RateLimitRepository:
    def __init__(self, conn):
        self.conn = conn

    def hit(self, bucket: str, window_start: int) -> int:
        return self.conn.execute(
            "INSERT INTO rate_limits (bucket, window_start, count) VALUES (?, ?, 1)"
            " ON CONFLICT(bucket) DO UPDATE SET"
            "   count = CASE WHEN rate_limits.window_start = excluded.window_start"
            "                THEN rate_limits.count + 1 ELSE 1 END,"
            "   window_start = excluded.window_start"
            " RETURNING count", (bucket, window_start)).fetchone()[0]

    def purge_before(self, cutoff: int):
        self.conn.execute("DELETE FROM rate_limits WHERE window_start < ?", (cutoff,))
