import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.dropr_scraper import parse_search_results

SAMPLE_DIR = ROOT / "tests" / "sample_data"
SCHEMA_PATH = ROOT / "db" / "schema.sql"

# action_dropr_sample.html and ici_paris_xl_dropr_sample.html are real
# (unmodified) snapshots of nl.action.jobs/vacatures/kantoor and
# werkenbijiciparisxl.nl/vacatures -- both run on Dropr CMS (confirmed via
# the dns-prefetch to cdnv2.dropr.io and the shared a.js-href.js-track link
# pattern), just with different per-client CSS class themes around it.
CASES = [
    ("action_dropr_sample.html", "https://nl.action.jobs", "Action"),
    ("ici_paris_xl_dropr_sample.html", "https://www.werkenbijiciparisxl.nl", "ICI Paris XL"),
]


def insert_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO jobs (source, external_id, title, company, location, url, description) "
        "VALUES (:source, :external_id, :title, :company, :location, :url, :description)",
        jobs,
    )
    conn.commit()


if __name__ == "__main__":
    for filename, base_url, source in CASES:
        html = (SAMPLE_DIR / filename).read_text()
        jobs = parse_search_results(html, base_url, source)

        assert len(jobs) >= 5, f"{source}: expected >=5 jobs, got {len(jobs)}"
        assert all(j["external_id"] for j in jobs), f"{source}: every job must have an external_id"
        assert all(j["title"] for j in jobs), f"{source}: every job must have a title"
        assert all(j["source"] == source for j in jobs), f"{source}: source mismatch"
        assert all(j["url"].startswith(base_url) for j in jobs), f"{source}: every job must have a full URL"
        assert all(j["location"] for j in jobs), f"{source}: every job must have a location"

        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA_PATH.read_text())

        insert_jobs(conn, jobs)
        insert_jobs(conn, jobs)  # same jobs again: dedupe on external_id must work

        count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        assert count == len(jobs), f"{source}: dedupe failed: {count} rows in db, expected {len(jobs)}"
        conn.close()

        print(f"{source}: {len(jobs)} jobs parsed, dedupe OK")
        print(f"{source} example:", jobs[0])

    print("Test passed")
