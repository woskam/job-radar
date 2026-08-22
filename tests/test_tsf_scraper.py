import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.tsf_scraper import parse_search_results

SAMPLE_DIR = ROOT / "tests" / "sample_data"
SCHEMA_PATH = ROOT / "db" / "schema.sql"

# tsf_sample.html is a real (unmodified) snapshot of
# https://vacatures.noord-holland.nl/vacatures -- TSF is an Angular SSR job
# platform ("Powered by TSF" in the footer) used by the province of
# Noord-Holland, presumably also by other government clients.
BASE_URL = "https://vacatures.noord-holland.nl"
SOURCE = "provincie_noord_holland"


def insert_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO jobs (source, external_id, title, company, location, url, description) "
        "VALUES (:source, :external_id, :title, :company, :location, :url, :description)",
        jobs,
    )
    conn.commit()


if __name__ == "__main__":
    html = (SAMPLE_DIR / "tsf_sample.html").read_text()
    jobs = parse_search_results(html, BASE_URL, SOURCE)

    assert len(jobs) >= 5, f"expected >=5 jobs, got {len(jobs)}"
    assert all(j["external_id"] for j in jobs), "every job must have an external_id"
    assert all(j["location"] for j in jobs), "every job must have a location"
    assert all(j["url"].startswith("https://vacatures.noord-holland.nl/vacatures/") for j in jobs), \
        "every job must have a full job URL"

    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_PATH.read_text())

    insert_jobs(conn, jobs)
    insert_jobs(conn, jobs)  # same jobs again: dedupe on external_id must work

    count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert count == len(jobs), f"dedupe failed: {count} rows in db, expected {len(jobs)} unique jobs"

    print(f"{len(jobs)} Noord-Holland jobs parsed, dedupe OK")
    print("example:", jobs[0])
    conn.close()
    print("Test passed")
