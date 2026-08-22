"""
NOTE: this script touches the real internet (Oracle Recruiting Cloud's
public recruitingCEJobRequisitions JSON API of Uber and JPMorgan Chase).
Does not run alongside the other tests/*.py (which work against saved
samples) -- run this deliberately and manually to check whether the live
Oracle integration still works.

Unlike test_workday_live.py and test_successfactors_live.py, this script has
NO dependency on scheduler.py or companies.yaml -- companies are hardcoded
here, so this can run standalone before the Oracle scraper is wired into the
scheduler/config.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.oracle_scraper import fetch_live_search

# host = the fa(.ocs).oraclecloud.com hostname from the candidate-experience
# link on the careers page; site_number = the "sites/{site_number}" segment in it.
ORACLE_COMPANIES = [
    {"name": "Uber", "host": "iaziqy.fa.ocs.oraclecloud.com", "site_number": "UberCareers"},
    {"name": "JPMorgan Chase", "host": "jpmc.fa.oraclecloud.com", "site_number": "CX_1001"},
]

# Amsterdam-focused search term, same as the Workday/SuccessFactors live
# tests -- filters server-side so we don't fetch thousands of jobs per company.
KEYWORD = "Amsterdam"

if __name__ == "__main__":
    all_jobs = []
    seen_sources = set()

    for company in ORACLE_COMPANIES:
        jobs = fetch_live_search(
            company["host"], company["site_number"], company["name"], keyword=KEYWORD, limit=25
        )
        print(f"{company['name']}: {len(jobs)} jobs for keyword={KEYWORD!r}")
        for job in jobs:
            assert job.keys() == {
                "source", "external_id", "title", "company", "location", "url", "description",
            }, f"unexpected fields in job dict: {job}"
            assert job["description"] is None
            assert job["url"].startswith(f"https://{company['host']}/")
        if jobs:
            seen_sources.add(company["name"])
        all_jobs.extend(jobs)

    assert len(all_jobs) > 0, "expected at least some jobs from Uber or JPMorgan Chase"
    print(f"\n{len(all_jobs)} jobs fetched from {len(seen_sources)}/{len(ORACLE_COMPANIES)} companies")

    missing = {c["name"] for c in ORACLE_COMPANIES} - seen_sources
    if missing:
        print(f"No results for: {', '.join(missing)} (may be fine, possibly no match on '{KEYWORD}')")

    print("\nSample results:")
    for job in all_jobs[:5]:
        print(f"  [{job['source']}] {job['title']} -- {job['location']}")
        print(f"    {job['url']}")

    print("\nTest passed (live)")
