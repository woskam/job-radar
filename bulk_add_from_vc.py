#!/usr/bin/env python3
"""
Bulk, non-interactive sibling to add_company.py, for VC portfolio pages
other than YCombinator (see bulk_add_from_yc.py for that one). Looks up a
candidate-lister function in vc_portfolios.py's VC_LISTERS registry, then
runs the same shared detect/verify/report pipeline as the YC script
(bulk_add_common.py) -- never writes to the real companies.yaml, only a
staging YAML file + plain-text report for manual review.

Usage:
  python bulk_add_from_vc.py --vc balderton [--limit N] [--offset N]
                              [--delay SECONDS] [--out PATH] [--report PATH]
"""
import argparse
from pathlib import Path

from bulk_add_common import run_bulk
from vc_portfolios import VC_LISTERS

SCRATCHPAD = Path("/tmp/claude-1000/-home-wychert-job/fa9cc262-587c-4ea2-9d80-ea925b05dd72/scratchpad")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--vc", required=True, choices=sorted(VC_LISTERS), help="Which VC's portfolio to pull")
    parser.add_argument("--limit", type=int, default=None, help="Max candidates to process this run")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many candidates from the start of the list")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds to sleep between requests (politeness, default 1.5)")
    parser.add_argument("--out", type=Path, default=None, help="Staging YAML output path (default: <scratchpad>/bulk_add_<vc>_staging.yaml)")
    parser.add_argument("--report", type=Path, default=None, help="Plain-text summary report path (default: <scratchpad>/bulk_add_<vc>_report.txt)")
    args = parser.parse_args()

    out = args.out or SCRATCHPAD / f"bulk_add_{args.vc}_staging.yaml"
    report = args.report or SCRATCHPAD / f"bulk_add_{args.vc}_report.txt"

    print(f"Fetching {args.vc}'s portfolio ...")
    candidates = VC_LISTERS[args.vc]()
    print(f"{len(candidates)} candidates found.")

    run_bulk(candidates, args.vc, args.delay, out, report, offset=args.offset, limit=args.limit)


if __name__ == "__main__":
    main()
