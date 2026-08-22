"""
NOTE: this script touches the real internet (L'Oréal's public Avature
career site). Does not run alongside the other tests/*.py -- run this
deliberately and manually to check whether the live integration still works.

Unlike the other *_live.py tests, this script has NO dependency on
scheduler.py/companies.yaml -- those don't yet contain an Avature entry
(that gets added separately). Company/keywords are hardcoded here.

Only L'Oréal Benelux is tested here: Goldman Sachs Amsterdam
(higher.gs.com/results) does NOT run on this classic Avature portal template
but on a custom Next.js/Apollo GraphQL app that expects a Bearer token for
the roleSearch query -- impossible to obtain without a logged-in browser
session, so we don't (yet) scrape that one. See scrapers/avature_scraper.py
for details.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.avature_scraper import fetch_live_search

COMPANIES = [
    {"name": "L'Oréal Benelux", "base_url": "https://careers.loreal.com"},
]

KEYWORDS = ["director", "senior manager", "digital sales", "wholesale", "ecommerce"]

if __name__ == "__main__":
    all_jobs = []
    seen_sources = set()

    for company in COMPANIES:
        for keyword in KEYWORDS:
            jobs = fetch_live_search(company["base_url"], company["name"], keywords=keyword)
            all_jobs.extend(jobs)
            if jobs:
                seen_sources.add(company["name"])

    unique_jobs = {(job["source"], job["external_id"]): job for job in all_jobs}
    assert len(unique_jobs) > 0, "expected at least some jobs"

    print(f"{len(unique_jobs)} unique jobs fetched from {len(seen_sources)}/{len(COMPANIES)} companies")

    missing = {c["name"] for c in COMPANIES} - seen_sources
    if missing:
        print(f"No results for: {', '.join(missing)} (may be fine, possibly no keyword match)")

    for job in list(unique_jobs.values())[:5]:
        print(" -", job)

    print("Test passed (live)")
