import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.wba_scraper import parse_search_results

SAMPLE_DIR = ROOT / "tests" / "sample_data"
SCHEMA_PATH = ROOT / "db" / "schema.sql"

# wba_sample.html is a real (unmodified) snapshot of
# https://werkenbij.amsterdam.nl/vacatures (page 1, 20 of the 43 jobs open at
# that time). Custom ASP.NET/Razor Pages CMS from the City of Amsterdam, no
# known ATS.
BASE_URL = "https://werkenbij.amsterdam.nl"
SOURCE = "gemeente_amsterdam"


def insert_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO jobs (source, external_id, title, company, location, url, description) "
        "VALUES (:source, :external_id, :title, :company, :location, :url, :description)",
        jobs,
    )
    conn.commit()


if __name__ == "__main__":
    html = (SAMPLE_DIR / "wba_sample.html").read_text()
    jobs = parse_search_results(html, BASE_URL, SOURCE)

    assert len(jobs) >= 5, f"expected >=5 jobs, got {len(jobs)}"
    assert all(j["external_id"] for j in jobs), "every job must have an external_id"
    assert all(len(j["external_id"]) == 36 for j in jobs), \
        "external_id must be the full UUID, not just the last hyphen-block"
    assert all(j["url"].startswith("https://werkenbij.amsterdam.nl/vacatures/") for j in jobs), \
        "every job must have a full job URL"

    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_PATH.read_text())

    insert_jobs(conn, jobs)
    insert_jobs(conn, jobs)  # same jobs again: dedupe on external_id must work

    count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert count == len(jobs), f"dedupe failed: {count} rows in db, expected {len(jobs)} unique jobs"

    print(f"{len(jobs)} Amsterdam jobs parsed, dedupe OK")
    print("example:", jobs[0])
    conn.close()
    print("Test passed")
