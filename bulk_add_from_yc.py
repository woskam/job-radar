#!/usr/bin/env python3
"""
Bulk, non-interactive sibling to add_company.py: pulls YCombinator's
"currently hiring" portfolio directory and runs every candidate through
add_company.py's existing ATS detectors + live verifiers, instead of the
usual one-URL-at-a-time interactive flow. Reuses that module's
fetch()/DETECTORS/VERIFIERS/build_entry() directly -- same detection logic,
same "blocked site -> stop, don't evade it" behavior, no duplication.

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
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
import yaml

from add_company import COMPANIES_PATH, DETECTORS, VERIFIERS, USER_AGENT, build_entry, fetch

YC_HIRING_URL = "https://yc-oss.github.io/api/companies/hiring.json"

# Most YC company websites don't embed an ATS fingerprint on the bare
# homepage -- they link to an internal /careers page that does (confirmed
# empirically: a first pilot run fetching only `website` found 0/30
# platforms). find_career_page() follows that link, or a handful of common
# guessed paths, before giving up -- same one-hop-deeper idea as a human
# clicking "Careers" in the nav before concluding a site has no known ATS.
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
_CAREER_KEYWORDS = ("career", "jobs", "join-us", "join_us", "we-are-hiring", "hiring")
CAREER_PATH_GUESSES = ["/careers", "/jobs", "/careers/", "/join-us", "/company/careers", "/about/careers"]


def _find_career_link(html: str, base_url: str) -> str | None:
    candidates = [href for href in _HREF_RE.findall(html) if any(k in href.lower() for k in _CAREER_KEYWORDS)]
    if not candidates:
        return None
    # Shortest match wins -- usually the direct nav link (e.g. "/careers")
    # rather than a longer URL that happens to contain "careers" as a
    # substring inside an unrelated blog post path.
    candidates.sort(key=len)
    return urljoin(base_url, candidates[0])


def find_career_page(website: str) -> requests.Response | None:
    """Returns the best page found to run DETECTORS against: the homepage if
    it already matches, else the homepage's own "careers" link if found and
    fetchable, else a few common guessed paths -- stopping at the first page
    where a detector matches. Falls back to the last successfully-fetched
    page (so a "no_platform" outcome still reports real HTML, not a guess
    that never loaded), or None if even the homepage was blocked/unreachable."""
    resp = fetch(website)
    if resp is None:
        return None
    if any(d(resp.text, website, resp.url) for d in DETECTORS):
        return resp

    link_url = _find_career_link(resp.text, resp.url)
    candidate_urls = ([link_url] if link_url else []) + [urljoin(website, p) for p in CAREER_PATH_GUESSES]

    last_ok = resp
    for url in candidate_urls:
        r = fetch(url)
        if r is None or r.status_code != 200:
            continue
        last_ok = r
        if any(d(r.text, url, r.url) for d in DETECTORS):
            return r
    return last_ok

SCRATCHPAD = Path("/tmp/claude-1000/-home-wychert-job/fa9cc262-587c-4ea2-9d80-ea925b05dd72/scratchpad")
DEFAULT_OUT = SCRATCHPAD / "bulk_add_yc_staging.yaml"
DEFAULT_REPORT = SCRATCHPAD / "bulk_add_yc_report.txt"


def load_existing_names(companies_path: Path = COMPANIES_PATH) -> set[str]:
    with open(companies_path) as f:
        data = yaml.safe_load(f)
    return {c["name"].strip().lower() for c in data.get("companies", [])}


def fetch_yc_candidates() -> list[dict]:
    resp = requests.get(YC_HIRING_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def yc_category(industry: str | None) -> str:
    if not industry or industry.strip().lower() == "unspecified":
        return "startup"
    return industry.strip().lower().replace(" ", "_").replace("/", "_")


def try_company(candidate: dict) -> tuple[str, dict | None]:
    """Returns (outcome, entry_or_None). outcome is one of "confirmed",
    "unverified" (platform detected but couldn't confirm a live posting),
    "no_platform", or "blocked" (same meaning as add_company.py's fetch())."""
    name = candidate.get("name", "").strip()
    website = candidate.get("website", "").strip()

    resp = find_career_page(website)
    if resp is None:
        return "blocked", None

    html = resp.text
    final_url = resp.url

    match = None
    for detector in DETECTORS:
        result = detector(html, final_url, final_url)
        if result:
            match = result
            break

    if not match:
        return "no_platform", None

    ats = match["ats"]
    missing = [k for k, v in match.items() if v is None]
    jobs, total = None, None
    if not missing:
        try:
            result = VERIFIERS[ats](match)
            jobs, total = result if isinstance(result, tuple) else (result, len(result))
        except Exception:
            jobs = None

    if not jobs:
        return "unverified", None

    entry = build_entry(name, yc_category(candidate.get("industry")), final_url, match, jobs, total)
    note = entry.pop("note")
    entry["segment"] = "startup"
    batch = candidate.get("batch")
    entry["note"] = f"{note}; YC batch {batch}" if batch else note
    return "confirmed", entry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None, help="Max candidates to process this run")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many candidates from the start of the YC list (for resuming in chunks)")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds to sleep between requests (politeness, default 1.5)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Staging YAML output path")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Plain-text summary report path")
    args = parser.parse_args()

    print(f"Fetching {YC_HIRING_URL} ...")
    candidates = fetch_yc_candidates()
    print(f"{len(candidates)} companies currently hiring per YC.")

    existing = load_existing_names()

    chunk = candidates[args.offset : args.offset + args.limit if args.limit else None]
    print(f"Processing candidates[{args.offset}:{args.offset + len(chunk)}] ({len(chunk)} of {len(candidates)}).")

    buckets: dict[str, list] = {"confirmed": [], "unverified": [], "no_platform": [], "blocked": [], "skipped_duplicate": [], "skipped_no_website": []}
    confirmed_entries = []

    for i, candidate in enumerate(chunk, start=1):
        name = (candidate.get("name") or "").strip()
        website = (candidate.get("website") or "").strip()

        if not name or name.lower() in existing:
            buckets["skipped_duplicate"].append(name or "(unnamed)")
            continue
        if not website:
            buckets["skipped_no_website"].append(name)
            continue

        print(f"[{i}/{len(chunk)}] {name} ({website}) ...", end=" ", flush=True)
        try:
            outcome, entry = try_company(candidate)
        except Exception as e:
            outcome, entry = "blocked", None
            print(f"error: {e}")
        else:
            print(outcome)

        if outcome == "confirmed":
            confirmed_entries.append(entry)
            buckets["confirmed"].append(name)
        else:
            buckets[outcome].append(f"{name} ({website})")

        time.sleep(args.delay)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        yaml.dump({"companies": confirmed_entries}, f, allow_unicode=True, sort_keys=False)

    report_lines = [f"Bulk YC add -- candidates[{args.offset}:{args.offset + len(chunk)}] of {len(candidates)}", ""]
    for bucket, items in buckets.items():
        report_lines.append(f"== {bucket} ({len(items)}) ==")
        report_lines.extend(f"  - {item}" for item in items)
        report_lines.append("")
    args.report.write_text("\n".join(report_lines))

    print(f"\nConfirmed {len(confirmed_entries)} companies. Staging file: {args.out}")
    print(f"Full report: {args.report}")
    print("Nothing was written to companies.yaml -- review the staging file, then merge it in by hand.")


if __name__ == "__main__":
    main()
