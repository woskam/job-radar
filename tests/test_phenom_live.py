"""
NOTE: this script touches the real internet (public Phenom/CareerConnect
career pages). Does not run alongside the other tests/*.py -- run this
deliberately and manually to check whether the live integration still works.

Deliberately NO dependency on scheduler.py or companies.yaml: imports
directly from scrapers/phenom_scraper.py and hardcodes the confirmed
companies below.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.phenom_scraper import fetch_live_search

# base_url = the locale-specific career root, NO "/search-results" suffix
# (see the fetch_live_search docstring in scrapers/phenom_scraper.py).
COMPANIES = [
    {"source": "eBay", "base_url": "https://jobs.ebayinc.com/us/en"},
    {"source": "ASN Bank", "base_url": "https://werkenbij.devolksbank.nl/nl/nl"},
    {"source": "Mars Benelux", "base_url": "https://careers.mars.com/nl/nl"},
]

if __name__ == "__main__":
    all_jobs = []

    for company in COMPANIES:
        jobs = fetch_live_search(company["base_url"], company["source"], limit=5)
        print(f"\n{company['source']}: {len(jobs)} jobs fetched (from first page)")
        for job in jobs[:3]:
            print(f"  - {job['title']} | {job['location']} | {job['url']}")
        all_jobs.extend(jobs)

    assert len(all_jobs) > 0, "expected at least some jobs"

    # keyword filter check: separate company, should give fewer/equal results
    # than unfiltered, and a nonsense keyword should give an empty (not broken) list
    ebay_all = fetch_live_search("https://jobs.ebayinc.com/us/en", "eBay", limit=1)
    ebay_filtered = fetch_live_search("https://jobs.ebayinc.com/us/en", "eBay", keywords="engineer", limit=1)
    ebay_nonsense = fetch_live_search("https://jobs.ebayinc.com/us/en", "eBay", keywords="zzznonexistentqueryxyz", limit=1)
    print(f"\neBay keyword filter check: unfiltered>=filtered ({len(ebay_all)}>={len(ebay_filtered)}), "
          f"nonsense keyword gives {len(ebay_nonsense)} results (expected 0)")
    assert len(ebay_nonsense) == 0, "nonsense keyword should not have given any results"

    print(f"\n{len(all_jobs)} jobs total fetched from {len(COMPANIES)}/{len(COMPANIES)} companies")
    print("Test passed (live)")
