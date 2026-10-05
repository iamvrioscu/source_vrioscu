#!/usr/bin/env python3
"""Restore a VRIOSCU website database from a backup made by backup_db.py.

STOP THE APPLICATION FIRST (sudo systemctl stop vrioscu). The script refuses to
run if it can see the live database is still open in WAL mode with a -wal file
that has content, unless --force is given.

Usage:
    python scripts/restore_db.py --backup /var/backups/vrioscu/vrioscu-20261005T020000Z.db.gz \
        --db /var/lib/vrioscu/vrioscu.db
"""
from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def restore(backup: Path, db: Path, force: bool = False) -> Path | None:
    if not backup.is_file():
        raise SystemExit(f"Backup not found: {backup}")
    wal = Path(str(db) + "-wal")
    if wal.exists() and wal.stat().st_size > 0 and not force:
        raise SystemExit("The live database has an active WAL file. Stop the application first, "
                         "or pass --force if you are sure it is stopped.")
    db.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=db.parent) as tmpdir:
        candidate = Path(tmpdir) / "restore.db"
        opener = gzip.open if backup.suffix == ".gz" else open
        with opener(backup, "rb") as f_in, open(candidate, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        conn = sqlite3.connect(candidate)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise SystemExit("Backup failed its integrity check. Nothing was changed.")
            versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
        finally:
            conn.close()
        previous = None
        if db.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            previous = db.with_name(f"{db.name}.pre-restore-{stamp}")
            os.replace(db, previous)
            os.chmod(previous, 0o600)
        for side in ("-wal", "-shm"):
            sp = Path(str(db) + side)
            if sp.exists():
                sp.unlink()
        os.chmod(candidate, 0o600)
        os.replace(candidate, db)
    print(f"Restored {db} from {backup} (migrations: {', '.join(versions)})")
    if previous:
        print(f"Previous database kept at {previous}. Delete it once you've confirmed the restore.")
    return previous


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--backup", required=True, type=Path)
    p.add_argument("--db", required=True, type=Path)
    p.add_argument("--force", action="store_true")
    a = p.parse_args(argv)
    os.umask(0o077)
    restore(a.backup, a.db, a.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
