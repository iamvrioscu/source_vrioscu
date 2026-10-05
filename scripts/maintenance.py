#!/usr/bin/env python3
"""Housekeeping: remove expired/revoked sessions and stale rate-limit buckets,
then run SQLite's optimiser. Safe to run while the site is live (e.g. daily)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_settings  # noqa: E402
from app.db import connect, migrate, transaction  # noqa: E402
from app.repositories import Repositories  # noqa: E402


def main() -> int:
    s = load_settings()
    migrate(s.database_path)
    conn = connect(s.database_path)
    try:
        r = Repositories(conn)
        with transaction(conn):
            r.sessions.purge_expired()
            r.rate_limits.purge_before(int(time.time()) - 86400)
        conn.execute("PRAGMA optimize")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    print("Maintenance complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
