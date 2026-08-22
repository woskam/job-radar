"""
NOTE: this script touches the real internet (public SAP SuccessFactors
Career Site Builder pages). Does not run alongside the other tests/*.py --
run this deliberately and manually to check whether the live integration
still works.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from matching.scorer import load_config
from scheduler import scrape_successfactors_live

if __name__ == "__main__":
    config = load_config()
    sf_companies = [c for c in config["companies"] if c.get("successfactors_base_url")]

    jobs = scrape_successfactors_live(config)

    assert len(jobs) > 0, "expected at least some jobs"
    seen_sources = {job["source"] for job in jobs}
    print(f"{len(jobs)} unique jobs fetched from {len(seen_sources)}/{len(sf_companies)} companies")

    missing = {c["name"] for c in sf_companies} - seen_sources
    if missing:
        print(f"No results for: {', '.join(missing)} (may be fine, possibly no keyword match)")

    print("Test passed (live)")
