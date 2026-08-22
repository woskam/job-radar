import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "job_radar.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()
    return conn


if __name__ == "__main__":
    # The self-test deliberately runs against a separate, disposable database
    # -- never against DB_PATH (the real job_radar.db) -- so this script is
    # always safe to re-run, even once the production db already has data.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        test_db_path = Path(tmp_dir) / "init_db_selftest.db"
        conn = init_db(test_db_path)

        conn.execute(
            "INSERT INTO jobs (source, external_id, title, company, location) "
            "VALUES (?, ?, ?, ?, ?)",
            ("test", "test-1", "Test Job", "Test BV", "Amsterdam"),
        )
        conn.commit()

        row = conn.execute(
            "SELECT source, external_id, title, company, location FROM jobs WHERE external_id = ?",
            ("test-1",),
        ).fetchone()
        print("Test record read back:", row)

        conn.close()
