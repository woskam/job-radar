import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.workday_scraper import parse_search_results

SAMPLE_DIR = ROOT / "tests" / "sample_data"
SCHEMA_PATH = ROOT / "db" / "schema.sql"

# workday_sample.json is a real (trimmed) snapshot of New Balance's public
# Workday CxS API, not synthetic like the earlier samples -- the JSON
# structure is API-driven and too specific to fake by hand.
HOST = "newbalance.wd1.myworkdayjobs.com"
SITE = "Careers"


def insert_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO jobs (source, external_id, title, company, location, url, description) "
        "VALUES (:source, :external_id, :title, :company, :location, :url, :description)",
        jobs,
    )
    conn.commit()


if __name__ == "__main__":
    data = json.loads((SAMPLE_DIR / "workday_sample.json").read_text())
    jobs = parse_search_results(data, host=HOST, site=SITE, source="new_balance")

    assert len(jobs) >= 5, f"expected >=5 jobs, got {len(jobs)}"
    assert all(j["external_id"] for j in jobs), "every job must have an external_id"
    assert all(j["url"].startswith("https://") for j in jobs), "every job must have a full url"

    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_PATH.read_text())

    insert_jobs(conn, jobs)
    insert_jobs(conn, jobs)  # same jobs again: dedupe on external_id must work

    count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert count == len(jobs), f"dedupe failed: {count} rows in db, expected {len(jobs)} unique jobs"

    print(f"{len(jobs)} jobs parsed, dedupe OK")
    print("example:", jobs[0])
    conn.close()
    print("Test passed")
