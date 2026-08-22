"""
NOTE: this script touches the real internet (jobs.deel.com, Klarna's public
job board). Deliberately decoupled from scheduler.py/companies.yaml -- run
this manually to check whether the live integration still works.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.deel_scraper import fetch_live_search

if __name__ == "__main__":
    jobs = fetch_live_search(company_slug="klarna", source="Klarna")

    assert len(jobs) > 0, "expected at least some jobs from Klarna"
    for job in jobs:
        assert job["source"] == "Klarna"
        assert job["company"] == "Klarna"
        assert job["external_id"]
        assert job["title"]
        assert job["url"].startswith("https://jobs.deel.com/klarna/job-details/")
        assert job["description"] is None

    print(f"{len(jobs)} jobs fetched from Klarna (deel, unfiltered/worldwide)")
    for job in jobs[:5]:
        print(f"  - {job['title']} | {job['location']} | {job['url']}")

    # Client-side location filter (the server ignores the query string, see
    # scrapers/deel_scraper.py) -- check that filtering on "Amsterdam" or
    # "Netherlands" works and returns a subset.
    nl_jobs = fetch_live_search(company_slug="klarna", source="Klarna", location="Amsterdam")
    print(f"{len(nl_jobs)} jobs filtered on location='Amsterdam'")
    assert len(nl_jobs) <= len(jobs)

    print("Test passed (live)")
