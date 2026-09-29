import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.lever_scraper import parse_search_results

SAMPLE_DIR = ROOT / "tests" / "sample_data"
SCHEMA_PATH = ROOT / "db" / "schema.sql"

# lever_sample.json is a real (unmodified) snapshot of
# https://api.lever.co/v0/postings/researchgate?mode=json -- Lever's own
# public, documented Postings API (github.com/lever/postings-api), no login
# needed. Fetched 2026-09-29.
HANDLE = "researchgate"
SOURCE = "ResearchGate"


def insert_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO jobs (source, external_id, title, company, location, url, description) "
        "VALUES (:source, :external_id, :title, :company, :location, :url, :description)",
        jobs,
    )
    conn.commit()


if __name__ == "__main__":
    data = json.loads((SAMPLE_DIR / "lever_sample.json").read_text())
    jobs = parse_search_results(data, HANDLE, SOURCE)

    assert len(jobs) >= 1, f"expected >=1 job, got {len(jobs)}"
    assert all(j["external_id"] for j in jobs), "every job must have an external_id"
    assert all(j["source"] == SOURCE for j in jobs), "source must be 'ResearchGate'"
    assert all(j["url"].startswith("https://jobs.lever.co/researchgate/") for j in jobs), \
        "every job must have a Lever hostedUrl"
    assert all(j["title"] for j in jobs), "every job must have a title"

    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_PATH.read_text())

    insert_jobs(conn, jobs)
    insert_jobs(conn, jobs)  # same jobs again: dedupe on external_id must work

    count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert count == len(jobs), f"dedupe failed: {count} rows in db, expected {len(jobs)} unique jobs"

    print(f"{len(jobs)} Lever jobs parsed, dedupe OK")
    print("example:", jobs[0])
    conn.close()
    print("Test passed")
