#!/usr/bin/env python3
"""
Bulk, non-interactive sibling to add_company.py: pulls YCombinator's
"currently hiring" portfolio directory and runs every candidate through
add_company.py's existing ATS detectors + live verifiers, instead of the
usual one-URL-at-a-time interactive flow. The actual detect/verify/report
pipeline lives in bulk_add_common.py (shared with bulk_add_from_vc.py for
other VC-portfolio sources) -- this module is just YC's candidate source.

Source: https://github.com/yc-oss/api -- a public, freely-hosted mirror of
YC's own Algolia companies directory (no official YC API exists), rebuilt
daily. companies/hiring.json is exactly the subset YC itself flags as
currently hiring.

Never writes to the real companies.yaml. Writes a staging YAML file (same
entry shape, ready to paste into companies.yaml's `companies:` list after a
manual review pass) plus a plain-text report, so hundreds of auto-detected
entries get eyeballed before they land in the shared, committed database --
same "trust but verify" spirit as reviewing add_company.py's own proposed
entry before answering y/N, just batched.

Usage:
  python bulk_add_from_yc.py [--limit N] [--offset N] [--delay SECONDS]
                              [--out PATH] [--report PATH]
"""
import argparse
from pathlib import Path

import requests

from add_company import USER_AGENT
from bulk_add_common import run_bulk

YC_HIRING_URL = "https://yc-oss.github.io/api/companies/hiring.json"

SCRATCHPAD = Path("/tmp/claude-1000/-home-wychert-job/fa9cc262-587c-4ea2-9d80-ea925b05dd72/scratchpad")
DEFAULT_OUT = SCRATCHPAD / "bulk_add_yc_staging.yaml"
DEFAULT_REPORT = SCRATCHPAD / "bulk_add_yc_report.txt"


def fetch_yc_candidates() -> list[dict]:
    resp = requests.get(YC_HIRING_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def yc_category(industry: str | None) -> str:
    if not industry or industry.strip().lower() == "unspecified":
        return "startup"
    return industry.strip().lower().replace(" ", "_").replace("/", "_")


def to_candidates(yc_companies: list[dict]) -> list[dict]:
    candidates = []
    for c in yc_companies:
        batch = c.get("batch")
        candidates.append({
            "name": (c.get("name") or "").strip(),
            "website": (c.get("website") or "").strip(),
            "category": yc_category(c.get("industry")),
            "source_note": f"YC batch {batch}" if batch else "sourced via YCombinator's public directory",
        })
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None, help="Max candidates to process this run")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many candidates from the start of the YC list (for resuming in chunks)")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds to sleep between requests (politeness, default 1.5)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Staging YAML output path")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Plain-text summary report path")
    args = parser.parse_args()

    print(f"Fetching {YC_HIRING_URL} ...")
    yc_companies = fetch_yc_candidates()
    print(f"{len(yc_companies)} companies currently hiring per YC.")
    candidates = to_candidates(yc_companies)

    run_bulk(candidates, "YC", args.delay, args.out, args.report, offset=args.offset, limit=args.limit)


if __name__ == "__main__":
    main()
