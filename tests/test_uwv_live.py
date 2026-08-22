"""
NOTE: this script touches the real internet (UWV's public
/nl/werken-bij/vacatures page -- server-side rendered JSON in the
first-results attribute, no login needed). Deliberately decoupled from
scheduler.py/companies.yaml -- run this manually to check whether the live
integration still works.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.uwv_scraper import fetch_live_search

if __name__ == "__main__":
    jobs = fetch_live_search()

    assert len(jobs) > 0, "expected at least some jobs from UWV"
    for job in jobs:
        assert job["source"] == "UWV"
        assert job["company"] == "UWV"
        assert job["external_id"]
        assert job["title"]
        assert job["url"].startswith("https://www.uwv.nl/")
        assert job["description"] is None

    print(f"{len(jobs)} jobs fetched from UWV")
    for job in jobs[:5]:
        print(f"  - {job['title']} | {job['location']} | {job['url']}")

    print("Test passed (live)")
