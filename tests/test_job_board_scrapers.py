import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.linkedin_scraper import parse_search_results as parse_linkedin
from scrapers.indeed_scraper import parse_search_results as parse_indeed

SAMPLE_DIR = ROOT / "tests" / "sample_data"
SCHEMA_PATH = ROOT / "db" / "schema.sql"


def insert_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO jobs (source, external_id, title, company, location, url, description) "
        "VALUES (:source, :external_id, :title, :company, :location, :url, :description)",
        jobs,
    )
    conn.commit()


def test_parser(sample_file: str, parse_fn, source: str) -> None:
    html = (SAMPLE_DIR / sample_file).read_text()
    jobs = parse_fn(html)
    assert len(jobs) >= 5, f"expected >=5 jobs from {sample_file}, got {len(jobs)}"

    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_PATH.read_text())

    insert_jobs(conn, jobs)
    insert_jobs(conn, jobs)  # same jobs again: dedupe on external_id must work

    count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert count == len(jobs), f"dedupe failed: {count} rows in db, expected {len(jobs)} unique jobs"

    conn.close()
    print(f"{source}: {len(jobs)} jobs parsed, dedupe OK")


if __name__ == "__main__":
    test_parser("linkedin_sample.html", parse_linkedin, "linkedin")
    test_parser("indeed_sample.html", parse_indeed, "indeed")
    print("All tests passed")
