"""
NOTE: this script touches the real internet (public Eightfold AI career
pages). Does not run alongside the other tests/*.py -- run this deliberately
and manually to check whether the live integration still works.

Decoupled from scheduler.py/companies.yaml: imports directly from
scrapers/eightfold_scraper.py, so this test keeps working regardless of
how/whether Eightfold companies end up in companies.yaml.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.eightfold_scraper import fetch_live_search

# Confirmed working (see scrapers/eightfold_scraper.py for an explanation of
# base_url vs. domain/group id). American Express (aexp.eightfold.ai) is
# deliberately not included: that tenant returns "Group ID not found:
# aexp.com" (HTTP 404) for every group id -- the account looks deprovisioned,
# AmEx's own careers site still links to it but the link is dead. No usable
# Eightfold layer there at the moment.
COMPANIES = [
    {"name": "Netflix", "base_url": "https://explore.jobs.netflix.net", "domain": "netflix.com", "location": "Amsterdam"},
    # Netherlands currently has 0 open jobs at HSBC (confirmed via curl on
    # /api/apply/v2/jobs?domain=hsbc.com&location=Netherlands) -- that's a
    # legitimate "no results" case, not a bug, hence the broader location
    # filter here so the live test still gets something back.
    {"name": "HSBC", "base_url": "https://portal.careers.hsbc.com", "domain": "hsbc.com", "location": "London"},
]

if __name__ == "__main__":
    all_jobs = []
    seen_sources = set()

    for company in COMPANIES:
        jobs = fetch_live_search(
            base_url=company["base_url"],
            domain=company["domain"],
            source=company["name"],
            location=company["location"],
            limit=30,
        )
        print(f"\n{company['name']}: {len(jobs)} jobs fetched")
        for job in jobs[:5]:
            print(f"  - {job['title']} | {job['location']} | {job['url']}")

        if jobs:
            seen_sources.add(company["name"])
        all_jobs.extend(jobs)

    assert len(all_jobs) > 0, "expected at least some jobs from the Eightfold companies"
    print(f"\n{len(all_jobs)} jobs fetched from {len(seen_sources)}/{len(COMPANIES)} companies")

    missing = {c["name"] for c in COMPANIES} - seen_sources
    if missing:
        print(f"No results (may be fine, possibly no keyword match) for: {', '.join(missing)}")

    # Sanity check on the required fields contract.
    expected_keys = {"source", "external_id", "title", "company", "location", "url", "description"}
    for job in all_jobs:
        assert set(job.keys()) == expected_keys, f"unexpected fields in job: {job}"
        assert job["description"] is None

    print("Test passed (live)")
