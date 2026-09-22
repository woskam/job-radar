#!/usr/bin/env python3
"""
Bulk, non-interactive sibling to add_company.py: imports Pegel Berlin's
public, CC0-licensed company export (pegel.berlin/data/companies.json) --
a curated list of Berlin startups with their ATS platform + board handle
already resolved, so unlike bulk_add_from_yc.py / bulk_add_from_vc.py, no
HTML fingerprinting via find_career_page()/DETECTORS is needed at all,
just live-verification via the platform's own public API
(try_company_known_ats() in bulk_add_common.py).

This is a ONE-TIME IMPORT, not a runtime dependency: pegel.berlin's own
site is fetched exactly once here, to learn which companies exist and
which ATS each uses. Every company added ends up scraped the normal way,
straight from its own ATS provider (scrapers/ashby_scraper.py etc.), same
as every other companies.yaml entry -- pegel.berlin is never touched again
after this import.

Why this source is fair game: pegel.berlin's own HTML pages sit behind an
active Cloudflare JS challenge (confirmed via a plain fetch AND a
browser-UA curl -- both got the "Just a moment..." page), so those are
correctly off-limits per this project's "don't evade active bot
protection" rule. But /data/companies.json itself returns a clean 200, no
challenge, and pegel.berlin's own robots.txt explicitly allows
ClaudeBot/Claude-User/Claude-SearchBot on everything except /admin/ and
/api/cron/ -- and llms.txt documents this export as CC0. Explicit
permission on an unprotected endpoint, not a bypass.

Only 5 of the ~14 ATS providers in Pegel's export are ones this project
already has a scraper for (ashby, greenhouse, recruitee, smartrecruiters,
deel) -- see SUPPORTED_PROVIDERS below for the mapping and
UNSUPPORTED_PROVIDER_NOTE for what's deliberately skipped (personio and
join.com are by far the largest: 146 and 85 companies respectively --
easily the highest-value next scrapers to build, just out of scope for
"import an existing export").

Never writes to the real companies.yaml. Writes a staging YAML file +
plain-text report, same review-before-merge discipline as the other
bulk_add_from_*.py scripts.

Usage:
  python bulk_add_from_pegel.py [--limit N] [--offset N] [--delay SECONDS]
                                 [--out PATH] [--report PATH]
"""
import argparse
import collections
from pathlib import Path

import requests

from add_company import USER_AGENT
from bulk_add_common import run_bulk, try_company_known_ats

PEGEL_COMPANIES_URL = "https://pegel.berlin/data/companies.json"

SCRATCHPAD = Path("/tmp/claude-1000/-home-wychert-job/fa9cc262-587c-4ea2-9d80-ea925b05dd72/scratchpad")
DEFAULT_OUT = SCRATCHPAD / "bulk_add_pegel_staging.yaml"
DEFAULT_REPORT = SCRATCHPAD / "bulk_add_pegel_report.txt"

# provider -> (companies.yaml ats name, companies.yaml field for the handle,
# template for a human-visitable career_url built from the handle -- Pegel's
# own `website` field is the company's marketing site, not its careers page).
SUPPORTED_PROVIDERS = {
    "ashby": ("ashby", "ashby_board_token", "https://jobs.ashbyhq.com/{handle}"),
    "greenhouse": ("greenhouse", "greenhouse_board_token", "https://boards.greenhouse.io/{handle}"),
    "recruitee": ("recruitee", "recruitee_company_slug", "https://{handle}.recruitee.com"),
    "smartrecruiters": ("smartrecruiters", "smartrecruiters_company_id", "https://jobs.smartrecruiters.com/{handle}/"),
    "deel": ("deel", "deel_company_slug", "https://jobs.deel.com/{handle}"),
}


def fetch_pegel_companies() -> list[dict]:
    resp = requests.get(PEGEL_COMPANIES_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def pegel_category(sector_primary: str | None) -> str:
    if not sector_primary:
        return "startup"
    return sector_primary.strip().lower().replace(" ", "_").replace("-", "_")


def to_candidates(pegel_companies: list[dict]) -> tuple[list[dict], collections.Counter]:
    """Returns (candidates, skipped_provider_counts) -- candidates only for
    the 5 supported providers among active companies; everything else
    (unsupported provider, or Workday's handle not mapping to
    workday_host+workday_site) is tallied but not attempted."""
    candidates = []
    skipped = collections.Counter()

    for c in pegel_companies:
        if c.get("status") != "active":
            continue
        provider = (c.get("ats_provider") or "").strip().lower()
        handle = (c.get("ats_handle") or "").strip()
        name = (c.get("name") or "").strip()

        if provider not in SUPPORTED_PROVIDERS or not handle or not name:
            skipped[provider or "(none)"] += 1
            continue

        ats, field, url_template = SUPPORTED_PROVIDERS[provider]
        candidates.append({
            "name": name,
            "website": url_template.format(handle=handle),
            "category": pegel_category(c.get("sector_primary")),
            "source_note": "sourced via Pegel Berlin's CC0 company export (pegel.berlin/data/companies.json)",
            "match": {"ats": ats, field: handle},
        })

    return candidates, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None, help="Max candidates to process this run")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many candidates from the start of the list")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds to sleep between requests (politeness, default 1.5)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Staging YAML output path")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Plain-text summary report path")
    args = parser.parse_args()

    print(f"Fetching {PEGEL_COMPANIES_URL} ...")
    pegel_companies = fetch_pegel_companies()
    print(f"{len(pegel_companies)} companies in Pegel's export.")

    candidates, skipped = to_candidates(pegel_companies)
    print(f"{len(candidates)} candidates on a supported ATS (ashby/greenhouse/recruitee/smartrecruiters/deel).")
    if skipped:
        print("Skipped (unsupported platform, no scraper yet):")
        for provider, count in skipped.most_common():
            print(f"  - {provider}: {count}")

    run_bulk(candidates, "Pegel", args.delay, args.out, args.report, offset=args.offset, limit=args.limit, try_fn=try_company_known_ats)


if __name__ == "__main__":
    main()
