#!/usr/bin/env python3
"""
Point this at a company's career/job-search page. It checks the raw HTML
against every ATS platform already supported in scrapers/, extracts the
fields that platform's companies.yaml entry needs, live-tests it against the
real scraper module (not just a fingerprint match), and -- if confirmed --
offers to append a working entry to companies.yaml for you.

Usage: python add_company.py <career-page-url> [--name "Company Name"] [--category "tech"]

Same hard rule as every scraper in this project: if the page is actively
blocked (WAF, CAPTCHA, connection reset), this reports that and stops --
it does not try to work around it. See CONTRIBUTING.md.
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
COMPANIES_PATH = ROOT / "companies.yaml"


def fetch(url: str) -> requests.Response | None:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20, allow_redirects=True)
    except requests.exceptions.RequestException as e:
        print(f"Could not reach {url}: {e}")
        print(
            "If this is a timeout or connection reset, the site is likely actively blocking "
            "automated requests -- document it as blocked in companies.yaml (see the existing "
            "'blocked' entries there for the convention), don't try to work around it."
        )
        return None
    if resp.status_code in (403, 429):
        print(f"{url} returned HTTP {resp.status_code} -- likely active bot protection (WAF/rate-limit).")
        print("Document it as blocked, don't try to evade it.")
        return None
    return resp


# --- Detectors --------------------------------------------------------------
# Each takes (html, requested_url, final_url_after_redirects) and returns a
# dict of the extra companies.yaml fields for that `ats` (a None value means
# "detected this platform, but couldn't auto-extract this specific field"),
# or None if this detector doesn't match at all. Order matters: the last two
# (SuccessFactors, Radancy) key off fairly generic substrings that can appear
# incidentally (e.g. an unrelated SF widget script), so more specific
# signatures get first try -- a false match here just fails the live test
# and gets reported honestly, it doesn't silently produce a bad entry.

def detect_workday(html, url, final_url):
    m = re.search(r'([a-z0-9-]+\.wd\d+\.myworkdayjobs\.com)/([^/"\'?]+)', html)
    if not m:
        return None
    return {"ats": "workday", "workday_host": m.group(1), "workday_site": m.group(2)}


def detect_greenhouse(html, url, final_url):
    m = re.search(r'(?:boards-api|job-boards|boards)\.greenhouse\.io/(?:v1/boards/|embed/job_board\?for=)?([a-zA-Z0-9_-]+)', html)
    if not m:
        return None
    return {"ats": "greenhouse", "greenhouse_board_token": m.group(1)}


def detect_ashby(html, url, final_url):
    m = re.search(r'jobs\.ashbyhq\.com/([a-zA-Z0-9._-]+)', html)
    if not m:
        return None
    return {"ats": "ashby", "ashby_board_token": m.group(1)}


def detect_smartrecruiters(html, url, final_url):
    m = re.search(r'jobs\.smartrecruiters\.com/([a-zA-Z0-9_-]+)/', html)
    if not m:
        return None
    return {"ats": "smartrecruiters", "smartrecruiters_company_id": m.group(1)}


def detect_phenom(html, url, final_url):
    m = re.search(r'widgetApiEndpoint["\']?\s*[:=]\s*["\']https?://([^/"\']+)/widgets', html)
    if m:
        host = m.group(1)
    elif "cdn.phenompeople.com" in html:
        host = urlparse(final_url).netloc
    else:
        return None
    path = urlparse(final_url).path.rstrip("/")
    return {"ats": "phenom", "phenom_base_url": f"https://{host}{path}"}


def detect_dropr(html, url, final_url):
    if "dropr.io" not in html and not re.search(r'class="[^"]*js-href[^"]*js-track[^"]*"', html):
        return None
    return {"ats": "dropr", "dropr_base_url": final_url.rstrip("/")}


def detect_eightfold(html, url, final_url):
    m = re.search(r'_EF_GROUP_ID\s*=\s*["\']([^"\']+)["\']', html)
    if not m:
        return None
    return {
        "ats": "eightfold",
        "eightfold_base_url": f"https://{urlparse(final_url).netloc}",
        "eightfold_domain": m.group(1),
    }


def detect_oracle(html, url, final_url):
    m = re.search(r'([a-z0-9-]+\.fa(?:\.[a-z0-9]+)?\.oraclecloud\.com)', html)
    if not m:
        return None
    site_m = re.search(r'siteNumber(?:%3D|=)([a-zA-Z0-9_]+)', html)
    return {
        "ats": "oracle_recruiting_cloud",
        "oracle_host": m.group(1),
        "oracle_site_number": site_m.group(1) if site_m else None,
    }


# Recruitee itself serves a generic analytics/tracking snippet from
# careers-analytics.recruitee.com that shows up in the raw HTML of many
# career sites regardless of whether they actually use Recruitee for their
# job board (found via Funda/Transavia both fingerprinting as "recruitee"
# with no real board behind it) -- these aren't company slugs, skip them.
_RECRUITEE_NON_COMPANY_SUBDOMAINS = {"www", "api", "cdn", "static", "assets", "careers-analytics", "analytics"}


def detect_recruitee(html, url, final_url):
    for slug in re.findall(r'([a-zA-Z0-9-]+)\.recruitee\.com', final_url + " " + html):
        if slug.lower() not in _RECRUITEE_NON_COMPANY_SUBDOMAINS:
            return {"ats": "recruitee", "recruitee_company_slug": slug}
    return None


def detect_deel(html, url, final_url):
    m = re.search(r'jobs\.deel\.com/([a-zA-Z0-9_-]+)', final_url) or re.search(r'jobs\.deel\.com/([a-zA-Z0-9_-]+)', html)
    if not m:
        return None
    return {"ats": "deel", "deel_company_slug": m.group(1)}


def detect_brassring(html, url, final_url):
    if "brassring.com" not in html and "brassring.com" not in final_url:
        return None
    haystack = html + final_url
    partner_m = re.search(r'partnerid=(\d+)', haystack, re.IGNORECASE)
    site_m = re.search(r'siteid=(\d+)', haystack, re.IGNORECASE)
    return {
        "ats": "brassring",
        "brassring_partner_id": partner_m.group(1) if partner_m else None,
        "brassring_site_id": site_m.group(1) if site_m else None,
    }


def detect_homerun(html, url, final_url):
    if "homerun.co" not in html:
        return None
    m = re.search(r'feed\.homerun\.co/([a-zA-Z0-9_-]+)', html)
    if m:
        return {"ats": "homerun", "homerun_feed_slug": m.group(1)}
    link_m = re.search(r'<link[^>]+type=["\']application/atom\+xml["\'][^>]+href=["\']([^"\']+)["\']', html)
    if link_m:
        slug_m = re.search(r'homerun\.co/([a-zA-Z0-9_-]+)', link_m.group(1))
        if slug_m:
            return {"ats": "homerun", "homerun_feed_slug": slug_m.group(1)}
    return {"ats": "homerun", "homerun_feed_slug": None}


def detect_avature(html, url, final_url):
    if "avature" not in html.lower():
        return None
    return {"ats": "avature", "avature_base_url": f"https://{urlparse(final_url).netloc}"}


def detect_jobylon(html, url, final_url):
    if "jobylon" not in html.lower():
        return None
    return {"ats": "jobylon", "jobylon_base_url": final_url.rstrip("/")}


def detect_getnoticed(html, url, final_url):
    if "getnoticed" not in html.lower() and "/api/vacancy" not in html:
        return None
    return {"ats": "getnoticed", "getnoticed_base_url": final_url.rstrip("/")}


def detect_successfactors(html, url, final_url):
    if "successfactors" not in html.lower():
        return None
    return {"ats": "sap_successfactors", "successfactors_base_url": final_url.rstrip("/")}


def detect_radancy(html, url, final_url):
    if "radancy" not in html.lower() and "cdn.radancy" not in html.lower():
        return None
    return {"ats": "radancy", "radancy_base_url": f"https://{urlparse(final_url).netloc}"}


DETECTORS = [
    detect_workday,
    detect_greenhouse,
    detect_ashby,
    detect_smartrecruiters,
    detect_phenom,
    detect_dropr,
    detect_eightfold,
    detect_oracle,
    detect_recruitee,
    detect_deel,
    detect_brassring,
    detect_homerun,
    detect_avature,
    detect_jobylon,
    detect_getnoticed,
    detect_successfactors,
    detect_radancy,
]


# --- Live verifiers ----------------------------------------------------------
# Each calls the real scraper module's own fetch_live_search -- confirming an
# actual posting comes back, not just that the fingerprint matched.

def verify_workday(fields):
    # fetch_live_search defaults to a single page of 20 -- data["total"] is
    # the tenant's real total posting count, not just this page's length
    # (found live: NXP reported "20 postings" here but data["total"] was 760).
    from scrapers.workday_scraper import fetch_live_search, parse_search_results
    data = fetch_live_search(host=fields["workday_host"], site=fields["workday_site"], search_text="")
    jobs = parse_search_results(data, host=fields["workday_host"], site=fields["workday_site"], source="test")
    return jobs, data.get("total")


def verify_greenhouse(fields):
    from scrapers.greenhouse_scraper import fetch_live_search
    return fetch_live_search(board_token=fields["greenhouse_board_token"], source="test")


def verify_ashby(fields):
    from scrapers.ashby_scraper import fetch_live_search
    return fetch_live_search(board_token=fields["ashby_board_token"], source="test")


def verify_smartrecruiters(fields):
    from scrapers.smartrecruiters_scraper import fetch_live_search
    return fetch_live_search(company_id=fields["smartrecruiters_company_id"], source="test")


def verify_phenom(fields):
    # Same page-size-cap issue as Workday -- refineSearch.totalHits is the
    # real total, not this page's length (found live: GSK reported "20
    # postings" here but totalHits was 703).
    from scrapers.phenom_scraper import _fetch_raw, parse_search_results
    data = _fetch_raw(base_url=fields["phenom_base_url"])
    jobs = parse_search_results(data, fields["phenom_base_url"], source="test")
    return jobs, data.get("refineSearch", {}).get("totalHits")


def verify_dropr(fields):
    from scrapers.dropr_scraper import fetch_live_search
    return fetch_live_search(base_url=fields["dropr_base_url"], source="test")


def verify_eightfold(fields):
    from scrapers.eightfold_scraper import fetch_live_search
    return fetch_live_search(base_url=fields["eightfold_base_url"], domain=fields["eightfold_domain"], source="test")


def verify_oracle(fields):
    # Same page-size-cap issue as Workday/Phenom -- items[0]["TotalJobsCount"]
    # is the tenant's real total, not this page's length (default limit=25;
    # found live: JPMorgan Chase's unfiltered call returns 25 requisitions on
    # this page but TotalJobsCount=7322).
    from scrapers.oracle_scraper import _fetch_raw, parse_search_results, parse_total_jobs_count
    data = _fetch_raw(host=fields["oracle_host"], site_number=fields["oracle_site_number"])
    jobs = parse_search_results(data, fields["oracle_host"], fields["oracle_site_number"], source="test")
    return jobs, parse_total_jobs_count(data)


def verify_recruitee(fields):
    from scrapers.recruitee_scraper import fetch_live_search
    return fetch_live_search(company_slug=fields["recruitee_company_slug"], source="test")


def verify_deel(fields):
    from scrapers.deel_scraper import fetch_live_search
    return fetch_live_search(company_slug=fields["deel_company_slug"], source="test")


def verify_brassring(fields):
    from scrapers.brassring_scraper import fetch_live_search
    return fetch_live_search(partner_id=fields["brassring_partner_id"], site_id=fields["brassring_site_id"], source="test")


def verify_homerun(fields):
    from scrapers.homerun_scraper import fetch_live_search
    return fetch_live_search(feed_slug=fields["homerun_feed_slug"], source="test")


def verify_avature(fields):
    from scrapers.avature_scraper import fetch_live_search
    return fetch_live_search(base_url=fields["avature_base_url"], source="test")


def verify_jobylon(fields):
    from scrapers.jobylon_scraper import fetch_live_search
    return fetch_live_search(base_url=fields["jobylon_base_url"], source="test")


def verify_getnoticed(fields):
    from scrapers.getnoticed_scraper import fetch_live_search
    return fetch_live_search(base_url=fields["getnoticed_base_url"], source="test")


def verify_successfactors(fields):
    # Same page-size-cap issue as Workday/Phenom, but only for tenants on the
    # newer JSON-API template -- _search returns (jobs, total) where total is
    # data["totalJobs"] there (found live: Triodos Bank reports totalJobs=21
    # but this single call alone returns 10). Older, fully server-side
    # rendered template tenants have no separate total; _search returns None
    # there, which the generic tuple-handling in main() treats the same as
    # "no total to cross-check" (same as a plain list return).
    from scrapers.successfactors_scraper import _search
    return _search(base_url=fields["successfactors_base_url"], source="test")


def verify_radancy(fields):
    # Same page-size-cap issue as Workday/Phenom -- fetch_live_search only
    # ever fetches page 1; data-total-job-results in the raw HTML is the
    # tenant's real total across all pages (found live: the Dutch
    # police/politie tenant has 95 total jobs across 7 pages of 15).
    from scrapers.radancy_scraper import _fetch_raw, parse_search_results, parse_total_results
    html = _fetch_raw(base_url=fields["radancy_base_url"])
    jobs = parse_search_results(html, fields["radancy_base_url"], source="test")
    return jobs, parse_total_results(html)


VERIFIERS = {
    "workday": verify_workday,
    "greenhouse": verify_greenhouse,
    "ashby": verify_ashby,
    "smartrecruiters": verify_smartrecruiters,
    "phenom": verify_phenom,
    "dropr": verify_dropr,
    "eightfold": verify_eightfold,
    "oracle_recruiting_cloud": verify_oracle,
    "recruitee": verify_recruitee,
    "deel": verify_deel,
    "brassring": verify_brassring,
    "homerun": verify_homerun,
    "avature": verify_avature,
    "jobylon": verify_jobylon,
    "getnoticed": verify_getnoticed,
    "sap_successfactors": verify_successfactors,
    "radancy": verify_radancy,
}

HINT_PATTERNS = [
    (r'([a-z0-9.-]+\.myworkdayjobs\.com)', "a myworkdayjobs.com host (but no matching /site/ path found nearby)"),
    (r'(__NEXT_DATA__|__NUXT__|window\.__)', "a client-side framework state blob -- results may load via a separate JS call"),
    (r'([a-z0-9.-]+\.(?:okta|auth0)\.com)', "an auth provider -- may require a logged-in session"),
    (r'(recaptcha|hcaptcha|cf-mitigated|Access Denied)', "a bot-protection signal"),
]


def print_hints(html: str) -> None:
    found_any = False
    for pattern, label in HINT_PATTERNS:
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            found_any = True
            print(f"  - {label}: {m.group(1)}")
    if not found_any:
        print("  (nothing recognizable found either -- likely needs the network tab of a real browser to trace)")


def build_entry(name: str, category: str, url: str, fields: dict, jobs: list | None, total: int | None = None) -> dict:
    entry = {"name": name, "category": category, "career_url": url}
    entry.update({k: v for k, v in fields.items() if v is not None and k != "ats"})
    entry["ats"] = fields["ats"]

    missing = [k for k, v in fields.items() if v is None]
    note_bits = [f"auto-detected via add_company.py on {date.today().isoformat()}"]
    if jobs:
        if total is not None and total != len(jobs):
            # Workday/Phenom only return one page (default 20) from this
            # verification call -- report the tenant's real total instead of
            # the page-size artifact, so the committed note isn't misleading.
            note_bits.append(f"confirmed {total} postings live (this page returns {len(jobs)})")
        else:
            note_bits.append(f"confirmed {len(jobs)} postings live")
    elif missing:
        note_bits.append(f"NOT verified live -- missing {', '.join(missing)}, add by hand")
    else:
        note_bits.append("NOT verified live -- check before trusting this entry")
    entry["note"] = "; ".join(note_bits)

    # Put ats and note back in a readable order (name/category/career_url,
    # then ats, then the platform-specific fields, then note last) --
    # dict insertion order above already achieves this except ats got
    # appended after the platform fields, so rebuild in the right order.
    ordered = {"name": entry["name"], "category": entry["category"], "career_url": entry["career_url"], "ats": entry["ats"]}
    for k, v in fields.items():
        if k != "ats" and v is not None:
            ordered[k] = v
    ordered["note"] = entry["note"]
    return ordered


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", help="The company's career/job-search page URL")
    parser.add_argument("--name", help="Company name for the companies.yaml entry (prompted if omitted)")
    parser.add_argument("--category", help="Category, e.g. tech/banking/fmcg/consulting (prompted if omitted)")
    args = parser.parse_args()

    print(f"Fetching {args.url} ...")
    resp = fetch(args.url)
    if resp is None:
        sys.exit(1)

    html = resp.text
    final_url = resp.url

    match = None
    for detector in DETECTORS:
        result = detector(html, args.url, final_url)
        if result:
            match = result
            break

    if not match:
        print("\nNo known ATS platform detected in the raw HTML.")
        print("This usually means results are loaded client-side via a JS call after page load,")
        print("or this is a genuinely new/custom platform. Things spotted that might help a manual look:")
        print_hints(html)
        print("\nSee CONTRIBUTING.md for what to do next.")
        sys.exit(1)

    ats = match["ats"]
    print(f"\nDetected platform: {ats}")
    missing = [k for k, v in match.items() if v is None]
    if missing:
        print(f"Could not auto-extract: {', '.join(missing)} -- you'll likely need the network tab of the apply flow for these.")

    jobs, total = None, None
    if not missing:
        print("Testing live...")
        try:
            result = VERIFIERS[ats](match)
            # Most verifiers return a plain job list (their scraper already
            # paginates through everything); Workday/Phenom return
            # (jobs, real_total) since their default call is a single
            # page -- len(jobs) alone would misreport the tenant's total.
            jobs, total = result if isinstance(result, tuple) else (result, len(result))
        except Exception as e:
            print(f"Live test failed: {e}")

    if jobs:
        if total is not None and total != len(jobs):
            print(f"\nConfirmed: {total} postings live ({len(jobs)} on this page). Sample:")
        else:
            print(f"\nConfirmed: {len(jobs)} postings found. Sample:")
        for j in jobs[:5]:
            print(f"  - {j.get('title')} | {j.get('location')}")
    else:
        print("\nCould not confirm live -- the entry below may still need fixing before it works.")

    name = args.name or input("\nCompany name for companies.yaml: ").strip()
    category = args.category or input("Category (e.g. tech, banking, fmcg, consulting): ").strip() or "tech"
    entry = build_entry(name, category, args.url, match, jobs, total)

    print("\n--- companies.yaml entry ---")
    entry_yaml = yaml.dump([entry], allow_unicode=True, sort_keys=False)
    print(entry_yaml)

    answer = input("Append this to companies.yaml? [y/N] ").strip().lower()
    if answer == "y":
        indented = "\n".join(("  " + line) if line.strip() else line for line in entry_yaml.splitlines())
        with open(COMPANIES_PATH, "a") as f:
            f.write("\n" + indented + "\n")
        print(f"Appended to {COMPANIES_PATH}.")
    else:
        print("Not written -- copy the block above into companies.yaml yourself when ready.")


if __name__ == "__main__":
    main()
