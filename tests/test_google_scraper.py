import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.google_scraper import parse_search_results

SAMPLE_DIR = ROOT / "tests" / "sample_data"
SCHEMA_PATH = ROOT / "db" / "schema.sql"

# google_careers_sample.html is a real (unmodified) snapshot of
# google.com/about/careers/applications/jobs/results/?location=Netherlands --
# confirmed live that the location filter is genuine (Germany returns a
# completely different job set), so every job in this fixture should carry
# "Netherlands" somewhere in its location string.
SOURCE = "Google"


def insert_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO jobs (source, external_id, title, company, location, url, description) "
        "VALUES (:source, :external_id, :title, :company, :location, :url, :description)",
        jobs,
    )
    conn.commit()


if __name__ == "__main__":
    html_text = (SAMPLE_DIR / "google_careers_sample.html").read_text()
    jobs = parse_search_results(html_text, SOURCE)

    assert len(jobs) >= 10, f"expected >=10 jobs, got {len(jobs)}"
    assert all(j["external_id"] for j in jobs), "every job must have an external_id"
    assert all(j["title"] for j in jobs), "every job must have a title"
    assert all(j["source"] == SOURCE for j in jobs), "source must be 'Google'"
    assert all(j["url"].startswith("https://www.google.com/") for j in jobs), \
        "every job must have a full Google URL"
    assert all("Netherlands" in (j["location"] or "") for j in jobs), \
        "every job in this NL-filtered fixture should have Netherlands in its location"
    assert any("&" in j["title"] for j in jobs), \
        "at least one title should contain an unescaped '&' (HTML entity decoding check)"

    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_PATH.read_text())

    insert_jobs(conn, jobs)
    insert_jobs(conn, jobs)  # same jobs again: dedupe on external_id must work

    count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert count == len(jobs), f"dedupe failed: {count} rows in db, expected {len(jobs)} unique jobs"

    print(f"{len(jobs)} Google jobs parsed, dedupe OK")
    print("example:", jobs[0])
    conn.close()
    print("Test passed")
