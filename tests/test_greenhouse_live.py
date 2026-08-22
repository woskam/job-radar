"""
NOTE: this script touches the real internet (Greenhouse's public Job Board
API for bol.com). Does not run alongside the other tests/*.py and has no
dependency on scheduler.py/companies.yaml -- run this deliberately and
manually to check whether the live integration still works.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.greenhouse_scraper import fetch_live_search

BOARD_TOKEN = "bolcom"
SOURCE = "bol.com"

if __name__ == "__main__":
    jobs = fetch_live_search(board_token=BOARD_TOKEN, source=SOURCE)

    assert len(jobs) > 0, "expected at least some jobs from bol.com"
    for job in jobs:
        assert job["source"] == SOURCE
        assert job["company"] == SOURCE
        assert job["external_id"]
        assert job["title"]
        assert job["url"].startswith("http")
        assert job["description"] is None

    print(f"{len(jobs)} jobs fetched from bol.com (board_token={BOARD_TOKEN})")
    print("example:", jobs[0])
    print("Test passed (live)")
