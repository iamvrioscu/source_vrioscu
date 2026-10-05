#!/usr/bin/env python3
"""Online, consistent SQLite backup for the VRIOSCU website.

Uses SQLite's backup API, so it is safe while the site is running (WAL mode).
Each backup is integrity-checked, gzip-compressed, written with 0600
permissions, and old backups beyond the retention window are removed.

Usage:
    python scripts/backup_db.py --db /var/lib/vrioscu/vrioscu.db \
        --dest /var/backups/vrioscu --keep-days 14
"""
from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

PREFIX = "vrioscu-"
SUFFIX = ".db.gz"


def backup(db: Path, dest: Path, keep_days: int) -> Path:
    if not db.is_file():
        raise SystemExit(f"Database not found: {db}")
    dest.mkdir(parents=True, exist_ok=True)
    os.chmod(dest, 0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final = dest / f"{PREFIX}{stamp}{SUFFIX}"

    with tempfile.TemporaryDirectory(dir=dest) as tmpdir:
        snapshot = Path(tmpdir) / "snapshot.db"
        src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        out = sqlite3.connect(snapshot)
        try:
            src.backup(out, pages=1024, sleep=0.05)
        finally:
            src.close()
        result = out.execute("PRAGMA integrity_check").fetchone()[0]
        out.close()
        if result != "ok":
            raise SystemExit(f"Integrity check failed on snapshot: {result}")
        tmp_gz = Path(tmpdir) / "snapshot.db.gz"
        with open(snapshot, "rb") as f_in, gzip.open(tmp_gz, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)
        os.chmod(tmp_gz, 0o600)
        os.replace(tmp_gz, final)

    cutoff = time.time() - keep_days * 86400
    for old in dest.glob(f"{PREFIX}*{SUFFIX}"):
        if old != final and old.stat().st_mtime < cutoff:
            old.unlink()
    return final


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", required=True, type=Path)
    p.add_argument("--dest", required=True, type=Path)
    p.add_argument("--keep-days", type=int, default=14)
    a = p.parse_args(argv)
    os.umask(0o077)
    path = backup(a.db, a.dest, a.keep_days)
    print(f"Backup written: {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
