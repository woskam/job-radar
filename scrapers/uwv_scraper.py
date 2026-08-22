import json

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
BASE_URL = "https://www.uwv.nl"
VACANCIES_PATH = "/nl/werken-bij/vacatures"


def parse_search_results(html: str, source: str) -> list[dict]:
    """
    UWV has NO known ATS-like separate JSON endpoint (it's a custom
    "Beagle"/"mdgs" web-component CMS), but the /nl/werken-bij/vacatures page
    renders ALL open jobs server-side, packed as JSON in the `first-results`
    attribute of the <mdgs-dynamic-list> custom element (no JS execution
    needed -- plain curl suffices). Confirmed: total-estimated="152" matched
    len(results) exactly -- all jobs are already in the first server render,
    so no pagination needed.
    """
    soup = BeautifulSoup(html, "lxml")
    el = soup.select_one("mdgs-dynamic-list")
    if el is None:
        return []

    raw = el.get("first-results")
    if not raw:
        return []

    data = json.loads(raw)
    jobs = []

    for posting in data.get("results", []):
        external_id = posting.get("id")
        if not external_id:
            continue

        href = posting.get("url") or ""
        url = href if href.startswith("http") else f"{BASE_URL}{href}"

        location = posting.get("location")
        region = posting.get("region")
        if location and region and region != location:
            location = f"{location}, {region}"
        else:
            location = location or region or None

        jobs.append({
            "source": source,
            "external_id": str(external_id),
            "title": posting.get("title"),
            "company": "UWV",
            "location": location,
            "url": url,
            "description": None,
        })

    return jobs


def fetch_live_search(source: str = "UWV") -> list[dict]:
    """
    UWV is NOT on werkenvoornederland.nl (it's an independent government
    agency (ZBO) with its own careers site, confirmed: 0 hits for "uwv" in
    werkenvoornederland.nl's sitemap-vacatures.xml). This separate job URL on
    uwv.nl itself (public, no login) returns the full current job list in a
    single GET call (tested: 152 jobs, no query param for keywords/pagination
    needed or found -- filtering on keywords therefore happens downstream in
    matching/scorer.py, same as with Greenhouse boards without a search
    parameter).
    """
    resp = requests.get(
        f"{BASE_URL}{VACANCIES_PATH}",
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    return parse_search_results(resp.text, source)
