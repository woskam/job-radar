"""
NOTE: this script touches the real internet (bunq's public Recruitee JSON
API). Deliberately decoupled from scheduler.py/companies.yaml -- run this
manually to check whether the live integration still works.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.recruitee_scraper import fetch_live_search

if __name__ == "__main__":
    jobs = fetch_live_search(company_slug="bunq", source="bunq")

    assert len(jobs) > 0, "expected at least some jobs from bunq"
    for job in jobs:
        assert job["source"] == "bunq"
        assert job["company"] == "bunq"
        assert job["external_id"]
        assert job["title"]
        assert job["url"].startswith("http")
        assert job["description"] is None

    print(f"{len(jobs)} jobs fetched from bunq (recruitee)")
    for job in jobs[:5]:
        print(f"  - {job['title']} | {job['location']} | {job['url']}")

    print("Test passed (live)")
