"""
NOTE: this script touches the real internet (HEMA's public Jobylon jobs
page). Does not run alongside the other tests/*.py and has no dependency on
scheduler.py/companies.yaml -- run this deliberately and manually to check
whether the live integration still works.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.jobylon_scraper import fetch_live_search

BASE_URL = "https://jobs.hema.com/nl/vacatures"
SOURCE = "HEMA"

if __name__ == "__main__":
    jobs = fetch_live_search(base_url=BASE_URL, source=SOURCE)

    assert len(jobs) > 0, "expected at least some jobs from HEMA"
    for job in jobs:
        assert job["source"] == SOURCE
        assert job["company"] == SOURCE
        assert job["external_id"]
        assert job["title"]
        assert job["url"].startswith("http")
        assert job["description"] is None

    print(f"{len(jobs)} jobs fetched from HEMA")
    print("example:", jobs[0])
    print("Test passed (live)")
