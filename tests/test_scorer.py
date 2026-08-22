import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db.migrations import ensure_columns
from scrapers.company_pages import parse_company_page
from matching.scorer import load_config, score_jobs

SAMPLE_DIR = ROOT / "tests" / "sample_data"
SCHEMA_PATH = ROOT / "db" / "schema.sql"


def insert_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO jobs (source, external_id, title, company, location, url, description) "
        "VALUES (:source, :external_id, :title, :company, :location, :url, :description)",
        jobs,
    )
    conn.commit()


if __name__ == "__main__":
    html = (SAMPLE_DIR / "adidas_sample.html").read_text()
    jobs = parse_company_page(html, "adidas")

    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_PATH.read_text())
    ensure_columns(conn)
    insert_jobs(conn, jobs)

    config = load_config()
    scored_count = score_jobs(conn, config)

    rows = conn.execute("SELECT title, relevance_score, status FROM jobs ORDER BY relevance_score DESC").fetchall()
    for title, score, status in rows:
        print(f"{score:>5} {status:>9}  {title}")

    assert all(score is not None for _, score, _ in rows), "every job must have a score"
    assert scored_count > 0, "expected at least 1 job above the threshold"
    assert scored_count < len(rows), "expected that not all jobs make it above the threshold"

    below = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'scored' AND relevance_score < ?",
                          (config["scoring"]["threshold"],)).fetchone()[0]
    assert below == 0, "a job below the threshold must not be passed on as 'scored'"

    conn.close()
    print(f"\n{scored_count}/{len(rows)} jobs above the threshold ({config['scoring']['threshold']})")
    print("Test passed")
