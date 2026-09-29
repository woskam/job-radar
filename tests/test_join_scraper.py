import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.join_scraper import NEXT_DATA_RE, parse_search_results, parse_total

SAMPLE_DIR = ROOT / "tests" / "sample_data"
SCHEMA_PATH = ROOT / "db" / "schema.sql"

# join_sample.html is a real (unmodified) snapshot of
# https://join.com/companies/naroiqcom -- join.com has no usable public API
# (their official API v2 requires a per-company token), but this public
# company page server-renders the job list into an embedded Next.js
# __NEXT_DATA__ block. Fetched 2026-09-29. NaroIQ only had 1 open role at
# fetch time -- small real company, not a fixture-quality issue, so this
# test checks >=1 rather than the usual >=5.
SLUG = "naroiqcom"
SOURCE = "NaroIQ"


def insert_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO jobs (source, external_id, title, company, location, url, description) "
        "VALUES (:source, :external_id, :title, :company, :location, :url, :description)",
        jobs,
    )
    conn.commit()


if __name__ == "__main__":
    html = (SAMPLE_DIR / "join_sample.html").read_text()
    match = NEXT_DATA_RE.search(html)
    assert match, "fixture must contain a __NEXT_DATA__ block"
    next_data = json.loads(match.group(1))

    jobs = parse_search_results(next_data, SLUG, SOURCE)
    total = parse_total(next_data)

    assert len(jobs) >= 1, f"expected >=1 job, got {len(jobs)}"
    assert total is not None and total >= len(jobs), f"total ({total}) must be >= len(jobs) ({len(jobs)})"
    assert all(j["external_id"] for j in jobs), "every job must have an external_id"
    assert all(j["source"] == SOURCE for j in jobs), "source must be 'NaroIQ'"
    assert all(j["url"].startswith(f"https://join.com/companies/{SLUG}/") for j in jobs), \
        "every job must have a join.com job-detail URL"
    assert all(j["title"] for j in jobs), "every job must have a title"

    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_PATH.read_text())

    insert_jobs(conn, jobs)
    insert_jobs(conn, jobs)  # same jobs again: dedupe on external_id must work

    count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert count == len(jobs), f"dedupe failed: {count} rows in db, expected {len(jobs)} unique jobs"

    print(f"{len(jobs)} join.com jobs parsed (of {total} total), dedupe OK")
    print("example:", jobs[0])
    conn.close()
    print("Test passed")
