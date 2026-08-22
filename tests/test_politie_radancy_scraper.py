import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.radancy_scraper import parse_search_results

SAMPLE_DIR = ROOT / "tests" / "sample_data"
SCHEMA_PATH = ROOT / "db" / "schema.sql"

# politie_radancy_sample.html is a real (unmodified) snapshot of
# https://www.mijnkombijdepolitie.nl/search-jobs?k=&l= -- the Dutch police
# run on the same Radancy/TalentBrew platform already supported by the
# existing radancy_scraper.py (confirmed: apikey= and cdn.radancy.eu
# references in the HTML, company/org id 3390), so NO new scraper module
# needed -- just add base_url "https://www.mijnkombijdepolitie.nl" and
# source="politie" to companies.yaml.
BASE_URL = "https://www.mijnkombijdepolitie.nl"
SOURCE = "politie"


def insert_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO jobs (source, external_id, title, company, location, url, description) "
        "VALUES (:source, :external_id, :title, :company, :location, :url, :description)",
        jobs,
    )
    conn.commit()


if __name__ == "__main__":
    html = (SAMPLE_DIR / "politie_radancy_sample.html").read_text()
    jobs = parse_search_results(html, BASE_URL, SOURCE)

    assert len(jobs) >= 5, f"expected >=5 jobs, got {len(jobs)}"
    assert all(j["external_id"] for j in jobs), "every job must have an external_id"
    assert all(j["source"] == SOURCE for j in jobs), "source must be 'politie'"
    assert all(j["url"].startswith("https://www.mijnkombijdepolitie.nl/") for j in jobs), \
        "every job must have a full politie URL"

    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_PATH.read_text())

    insert_jobs(conn, jobs)
    insert_jobs(conn, jobs)  # same jobs again: dedupe on external_id must work

    count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert count == len(jobs), f"dedupe failed: {count} rows in db, expected {len(jobs)} unique jobs"

    print(f"{len(jobs)} politie jobs parsed, dedupe OK")
    print("example:", jobs[0])
    conn.close()
    print("Test passed")
