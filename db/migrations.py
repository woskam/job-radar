import sqlite3

# Small, lightweight column migration instead of a migration framework --
# SQLite's ALTER TABLE ADD COLUMN has no IF NOT EXISTS, so we check
# pragma table_info() ourselves before adding a column.
NEW_JOB_COLUMNS = {
    "rejected_at": "TIMESTAMP",
    "rejected_stage": "TEXT",  # scoring / approval / review (relevance_check: historical, no longer actively written)
    "rejected_reason": "TEXT",
    "telegram_message_id": "INTEGER",
    "sent_at": "TIMESTAMP",
}

NEW_LETTER_COLUMNS = {
    "language": "TEXT",  # 'nl' / 'en', detected at generation time -- avoids re-detecting on download
}


def _ensure_table_columns(conn: sqlite3.Connection, table: str, new_columns: dict[str, str]) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, col_type in new_columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")


def ensure_columns(conn: sqlite3.Connection) -> None:
    # WAL instead of the default rollback journal: now that several processes
    # (scheduler, approval_worker, dashboard) can run against the same db at
    # the same time, a writer would otherwise block readers too.
    conn.execute("PRAGMA journal_mode=WAL")

    _ensure_table_columns(conn, "jobs", NEW_JOB_COLUMNS)
    _ensure_table_columns(conn, "letters", NEW_LETTER_COLUMNS)
    conn.commit()
