"""
NOTE: this script touches the real internet (Workday's public CxS API of
every configured tenant) and takes ~1 minute. It does not run alongside the
other tests/*.py (which all work against saved samples) -- run this
deliberately and manually if you want to check whether the live Workday
integration still works.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from matching.scorer import load_config
from scheduler import scrape_workday_live

if __name__ == "__main__":
    config = load_config()
    workday_companies = [c for c in config["companies"] if c.get("ats") == "workday"]

    jobs = scrape_workday_live(config)

    assert len(jobs) > 0, "expected at least some jobs from the Workday companies"
    seen_sources = {job["source"] for job in jobs}
    print(f"{len(jobs)} unique jobs fetched from {len(seen_sources)}/{len(workday_companies)} companies")

    missing = {c["name"] for c in workday_companies} - seen_sources
    if missing:
        print(f"No results (may be fine, possibly no keyword match) for: {', '.join(missing)}")

    print("Test passed (live)")
