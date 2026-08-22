"""
NOTE: this script touches the real internet (Guess' public BrassRing
Talent Gateway, sjobs.brassring.com). Deliberately decoupled from
scheduler.py/companies.yaml -- run this manually to check whether the live
integration still works.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.brassring_scraper import fetch_live_search

if __name__ == "__main__":
    # partner_id/site_id for Guess' Corporate Careers site, found via a search
    # engine (sjobs.brassring.com/TGnewUI/Search/Home/Home?partnerid=25813&siteid=5178)
    jobs = fetch_live_search(partner_id="25813", site_id="5178", source="Guess")

    assert len(jobs) > 0, "expected at least some jobs from Guess"
    for job in jobs:
        assert job["source"] == "Guess"
        assert job["company"] == "Guess"
        assert job["external_id"]
        assert job["title"]
        assert job["url"].startswith("http")
        assert job["description"] is None
        # NOTE: BrassRing/Guess doesn't return a location per job (see
        # scrapers/brassring_scraper.py) -- so location is always None.
        assert job["location"] is None

    print(f"{len(jobs)} jobs fetched from Guess (brassring, unfiltered)")
    for job in jobs[:5]:
        print(f"  - {job['title']} | {job['url']}")

    # Server-side keyword filter check
    sales_jobs = fetch_live_search(partner_id="25813", site_id="5178", source="Guess", keywords="sales")
    print(f"{len(sales_jobs)} jobs filtered on keyword='sales'")
    assert len(sales_jobs) <= len(jobs)

    print("Test passed (live)")
