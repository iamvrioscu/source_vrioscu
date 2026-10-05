"""SQLite connection management, transactions and migrations.

Only the repository modules issue SQL. Everything above them works with
plain dicts, so the storage engine can be swapped (see docs/ARCHITECTURE.md).
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .time_utils import now_iso

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _secure_path(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except PermissionError:
        pass
    if not path.exists():
        fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
    try:
        os.chmod(path, 0o600)
    except PermissionError:
        pass


def connect(path: Path) -> sqlite3.Connection:
    _secure_path(path)
    # isolation_level=None: we control transactions explicitly via transaction().
    conn = sqlite3.connect(str(path), timeout=10, isolation_level=None, check_same_thread=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection, immediate: bool = True):
    """Atomic unit of work. Nested calls become savepoints."""
    if conn.in_transaction:
        name = f"sp_{id(conn)}_{os.urandom(3).hex()}"
        conn.execute(f"SAVEPOINT {name}")
        try:
            yield conn
        except BaseException:
            conn.execute(f"ROLLBACK TO {name}")
            conn.execute(f"RELEASE {name}")
            raise
        conn.execute(f"RELEASE {name}")
        return
    conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def migrate(path: Path) -> list[str]:
    """Apply pending migrations/*.sql in filename order. Returns applied versions."""
    conn = connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
        applied = []
        for file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = file.stem
            if version in done:
                continue
            sql = file.read_text(encoding="utf-8")
            try:
                conn.executescript(
                    "BEGIN;\n" + sql + "\n;INSERT INTO schema_migrations(version, applied_at) "
                    f"VALUES ('{version}', '{now_iso()}');\nCOMMIT;"
                )
            except sqlite3.Error:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            applied.append(version)
        for suffix in ("-wal", "-shm"):
            side = Path(str(path) + suffix)
            if side.exists():
                try:
                    os.chmod(side, 0o600)
                except PermissionError:
                    pass
        return applied
    finally:
        conn.close()
