"""
NOTE: this script touches the real internet (public GetNoticed career sites
of KPN and Odido). Does not run alongside the other tests/*.py (which all
work against saved samples) -- run this deliberately and manually to check
whether the live integration still works.

Deliberately DECOUPLED from scheduler.py/companies.yaml: companies are
hardcoded here, so this test keeps working regardless of how
getnoticed_scraper is eventually wired into scheduler.py.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.getnoticed_scraper import fetch_live_search

GETNOTICED_COMPANIES = [
    {"name": "KPN", "career_url": "https://jobs.kpn.com/vacatures"},
    {"name": "Odido", "career_url": "https://werkenbij.odido.nl/vacatures"},
]

EXPECTED_KEYS = {"source", "external_id", "title", "company", "location", "url", "description"}

if __name__ == "__main__":
    all_jobs: list[dict] = []
    seen_sources: set[str] = set()

    for company in GETNOTICED_COMPANIES:
        # without a keyword: should return the full (paginated) list
        jobs = fetch_live_search(company["career_url"], company["name"])
        print(f"{company['name']}: {len(jobs)} jobs (no keyword filter)")

        assert len(jobs) > 0, f"expected at least some jobs for {company['name']}"

        ids = [job["external_id"] for job in jobs]
        assert len(ids) == len(set(ids)), f"duplicate external_ids for {company['name']}"

        for job in jobs:
            assert set(job.keys()) == EXPECTED_KEYS, f"unexpected fields: {job.keys()}"
            assert job["source"] == company["name"]
            assert job["company"] == company["name"]
            assert job["title"], f"empty title: {job}"
            assert job["url"].startswith("http"), f"not an absolute url: {job}"
            assert job["description"] is None, "description must always be None"

        # with a keyword: result must be a subset (server-side filter)
        keyword = "sales" if company["name"] == "Odido" else "engineer"
        filtered = fetch_live_search(company["career_url"], company["name"], keywords=keyword)
        print(f"{company['name']}: {len(filtered)} jobs with keyword '{keyword}'")
        assert len(filtered) <= len(jobs), (
            f"keyword filter for {company['name']} returned more results than unfiltered "
            "-- the search param apparently no longer filters server-side, re-check with curl"
        )
        assert {j["external_id"] for j in filtered} <= {j["external_id"] for j in jobs}

        seen_sources.add(company["name"])
        all_jobs.extend(jobs)

    missing = {c["name"] for c in GETNOTICED_COMPANIES} - seen_sources
    if missing:
        print(f"No results for: {', '.join(missing)} (may be fine, possibly no keyword match)")

    print(f"Total {len(all_jobs)} unique jobs fetched from {len(seen_sources)}/{len(GETNOTICED_COMPANIES)} companies")
    print("Test passed (live)")
