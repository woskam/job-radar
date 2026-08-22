import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db.migrations import ensure_columns
from letters.generator import load_projects, generate_letter, save_letter

SCHEMA_PATH = ROOT / "db" / "schema.sql"


if __name__ == "__main__":
    assert os.environ.get("DRY_RUN", "true").lower() == "true", "run this test with DRY_RUN=true"

    mock_job = {
        "title": "Director Digital Sales Benelux",
        "company": "Mock Retail Group",
        "location": "Amsterdam, Netherlands",
        "description": "We zoeken een Director Digital Sales met ervaring in ecommerce en wholesale.",
    }

    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_PATH.read_text())
    ensure_columns(conn)
    cursor = conn.execute(
        "INSERT INTO jobs (source, external_id, title, company, location, description, status) "
        "VALUES ('mock', 'mock-1', ?, ?, ?, ?, 'scored')",
        (mock_job["title"], mock_job["company"], mock_job["location"], mock_job["description"]),
    )
    job_id = cursor.lastrowid
    conn.commit()

    projects = load_projects()
    draft = generate_letter(mock_job, cv_text="[mock cv]", projects=projects, dry_run=True)

    assert draft.strip(), "draft must not be empty"
    assert "DRY_RUN" in draft, "dry-run draft must be clearly marked, no real API call"

    save_letter(conn, job_id, draft)

    status = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()[0]
    assert status == "letter_drafted", f"expected status letter_drafted, got {status}"

    saved_draft = conn.execute("SELECT draft FROM letters WHERE job_id = ?", (job_id,)).fetchone()[0]
    assert saved_draft == draft

    conn.close()
    print(draft)
    print("Test passed (DRY_RUN, no real API call)")
