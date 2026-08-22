"""
NOTE: this script touches the real internet (werkenvoornederland.nl, the
Dutch central government's public job portal, via the Hippo/BloomReach
"component-rendering" AJAX endpoint -- no login needed). Deliberately kept
decoupled from scheduler.py/companies.yaml -- run this manually to check
whether the live integration still works.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.werkenvoornederland_scraper import fetch_live_search

# (term, employer_match, source) -- employer_match=None means no extra
# client-side filter (for MIVD, the standalone text "MIVD" is already
# specific enough in the employer field itself).
CASES = [
    ("MIVD", "Militaire Inlichtingen", "MIVD"),
    ("AIVD", "Algemene Inlichtingen- en Veiligheidsdienst", "AIVD"),
    ("Rijkswaterstaat", "Rijkswaterstaat", "Rijkswaterstaat"),
    ("Belastingdienst", "Belastingdienst", "Belastingdienst"),
    ("Douane", "Douane", "Douane"),
    ("DUO", "Dienst Uitvoering Onderwijs", "DUO"),
]

if __name__ == "__main__":
    for i, (term, employer_match, source) in enumerate(CASES):
        if i > 0:
            time.sleep(1.0)  # respect werkenvoornederland.nl's robots.txt Request-rate
        jobs = fetch_live_search(term=term, source=source, employer_match=employer_match, max_pages=3)

        assert len(jobs) > 0, f"expected at least some jobs for {source}"
        for job in jobs:
            assert job["source"] == source
            assert job["external_id"]
            assert job["title"]
            assert job["url"].startswith("https://www.werkenvoornederland.nl/")
            assert job["description"] is None
            assert employer_match.lower() in (job["company"] or "").lower()

        print(f"{source}: {len(jobs)} jobs (term={term!r}, employer_match={employer_match!r})")
        print("  example:", jobs[0])

    print("Test passed (live)")
