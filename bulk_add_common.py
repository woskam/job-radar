"""
Shared pipeline behind every bulk_add_from_*.py script: given a list of
candidates in the common shape below, runs each through add_company.py's
existing ATS detectors + live verifiers (via find_career_page/try_company),
then writes a staging YAML file + plain-text report for manual review --
never touches the real companies.yaml directly. Split out of
bulk_add_from_yc.py once a second source (VC portfolio pages, see
vc_portfolios.py) needed the exact same loop/dedup/report logic with a
different candidate source.

Common candidate shape: {"name", "website", "category", "source_note"}.
`source_note` is appended to the auto-generated note (e.g. "YC batch W12",
"sourced via Balderton Capital's public portfolio page").
"""
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
import yaml

from add_company import COMPANIES_PATH, DETECTORS, VERIFIERS, build_entry, fetch

# Most company websites don't embed an ATS fingerprint on the bare homepage
# -- they link to an internal /careers page that does (confirmed empirically
# on the YC pass: a first pilot run fetching only `website` found 0/30
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


def load_existing_names(companies_path: Path = COMPANIES_PATH) -> set[str]:
    with open(companies_path) as f:
        data = yaml.safe_load(f)
    return {c["name"].strip().lower() for c in data.get("companies", [])}


def verify_and_build(name: str, category: str, career_url: str, match: dict, source_note: str | None) -> tuple[str, dict | None]:
    """Shared tail of both detection paths: given an already-identified ATS
    `match` dict (whether found via DETECTORS or already known from the
    candidate's own source), live-verifies it and builds a companies.yaml
    entry. Returns (outcome, entry_or_None), outcome one of "confirmed" or
    "unverified" (missing fields, or no live posting confirmed)."""
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

    entry = build_entry(name, category, career_url, match, jobs, total)
    note = entry.pop("note")
    entry["segment"] = "startup"
    entry["note"] = f"{note}; {source_note}" if source_note else note
    return "confirmed", entry


def try_company(candidate: dict) -> tuple[str, dict | None]:
    """Returns (outcome, entry_or_None). outcome is one of "confirmed",
    "unverified" (platform detected but couldn't confirm a live posting),
    "no_platform", or "blocked" (same meaning as add_company.py's fetch()).
    Discovers the ATS via find_career_page()/DETECTORS -- for a candidate
    that already knows its ATS (e.g. Pegel's export), skip straight to
    verify_and_build() instead."""
    name = candidate["name"].strip()
    website = candidate["website"].strip()

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

    return verify_and_build(name, candidate["category"], final_url, match, candidate.get("source_note"))


def try_company_known_ats(candidate: dict) -> tuple[str, dict | None]:
    """Like try_company(), but for a candidate whose ATS is already known
    (candidate["match"], same shape add_company.py's DETECTORS return) --
    skips find_career_page()/DETECTORS entirely and never touches the
    company's own website, just its ATS's public API. Used for sources
    that publish the mapping themselves (e.g. Pegel Berlin's companies.json:
    ats_provider + ats_handle already resolved)."""
    name = candidate["name"].strip()
    career_url = candidate["website"].strip()
    return verify_and_build(name, candidate["category"], career_url, candidate["match"], candidate.get("source_note"))


def run_bulk(
    candidates: list[dict],
    label: str,
    delay: float,
    out: Path,
    report: Path,
    offset: int = 0,
    limit: int | None = None,
    try_fn=try_company,
) -> None:
    """Runs try_company() over candidates[offset:offset+limit], skipping
    names already in companies.yaml or with no website, and writes a
    staging YAML file (ready to paste into companies.yaml's `companies:`
    list after review) plus a plain-text bucket report. Never writes to the
    real companies.yaml."""
    existing = load_existing_names()

    chunk = candidates[offset : offset + limit if limit else None]
    print(f"Processing {label} candidates[{offset}:{offset + len(chunk)}] ({len(chunk)} of {len(candidates)}).")

    buckets: dict[str, list] = {
        "confirmed": [], "unverified": [], "no_platform": [], "blocked": [],
        "skipped_duplicate": [], "skipped_no_website": [],
    }
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
            outcome, entry = try_fn(candidate)
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

        time.sleep(delay)

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        yaml.dump({"companies": confirmed_entries}, f, allow_unicode=True, sort_keys=False)

    report_lines = [f"Bulk add ({label}) -- candidates[{offset}:{offset + len(chunk)}] of {len(candidates)}", ""]
    for bucket, items in buckets.items():
        report_lines.append(f"== {bucket} ({len(items)}) ==")
        report_lines.extend(f"  - {item}" for item in items)
        report_lines.append("")
    report.write_text("\n".join(report_lines))

    print(f"\nConfirmed {len(confirmed_entries)} companies. Staging file: {out}")
    print(f"Full report: {report}")
    print("Nothing was written to companies.yaml -- review the staging file, then merge it in by hand.")
