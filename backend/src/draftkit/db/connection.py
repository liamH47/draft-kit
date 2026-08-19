"""SQLite connection + migration runner.

WAL mode so a reader (the draft board polling) never blocks the writer
(recording a pick). Migrations are numbered .sql files applied once, in name
order, at startup — no migration framework for a single-file database.
"""

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=FULL")  # a pick must survive kill -9
    return conn


def migrate(conn: sqlite3.Connection) -> list[str]:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migration (name TEXT PRIMARY KEY)")
    applied = {row["name"] for row in conn.execute("SELECT name FROM schema_migration")}
    newly_applied = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        with conn:
            conn.executescript(path.read_text())
            conn.execute("INSERT INTO schema_migration (name) VALUES (?)", (path.name,))
        newly_applied.append(path.name)
    return newly_applied
