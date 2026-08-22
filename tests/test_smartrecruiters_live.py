"""
NOTE: this script touches the real internet (SmartRecruiters' public
Posting API of each company listed below) and does not run alongside the
other tests/*.py (which all work against saved samples or go through
scheduler.py/companies.yaml) -- deliberately kept decoupled from
scheduler.py/companies.yaml so this also works before those are updated.
Run this deliberately and manually to check whether the live
SmartRecruiters integration still works.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.smartrecruiters_scraper import fetch_live_search

# company_id = the identifier as it appears in the careers.smartrecruiters.com/{id} URL
COMPANIES = [
    {"company_id": "ASICS", "source": "ASICS"},
    {"company_id": "wehkamp", "source": "wehkamp"},
]

REQUIRED_FIELDS = {"source", "external_id", "title", "company", "location", "url", "description"}

if __name__ == "__main__":
    all_jobs = []
    working = []
    broken = []

    for c in COMPANIES:
        print(f"--- {c['source']} (companyId={c['company_id']}) ---")
        try:
            jobs = fetch_live_search(c["company_id"], c["source"])
        except Exception as e:
            print(f"ERROR: {e}")
            broken.append(c["source"])
            continue

        if not jobs:
            print("No jobs found (may be fine if there just happen to be 0 open right now)")
            working.append(c["source"])
            continue

        for job in jobs:
            assert set(job.keys()) == REQUIRED_FIELDS, f"unexpected fields: {job.keys()}"
            assert job["external_id"], "external_id must not be empty"
            assert job["title"], "title must not be empty"
            assert job["url"].startswith("https://jobs.smartrecruiters.com/"), job["url"]

        print(f"{len(jobs)} jobs fetched")
        for job in jobs[:3]:
            print(f"  - [{job['external_id']}] {job['title']} -- {job['location']}")
            print(f"    {job['url']}")

        working.append(c["source"])
        all_jobs.extend(jobs)

    print()
    print(f"Worked: {', '.join(working) if working else '(none)'}")
    print(f"Didn't work: {', '.join(broken) if broken else '(none)'}")

    assert not broken, f"these companies failed: {broken}"
    assert all_jobs, "expected at least some jobs in total"

    print(f"\n{len(all_jobs)} jobs total from {len(working)}/{len(COMPANIES)} companies")
    print("Test passed (live)")
