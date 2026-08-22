import re

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TRAILING_ID_RE = re.compile(r"-(\d+)$")


def parse_search_results(html: str, source: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs: dict[str, dict] = {}

    for link in soup.select("a.vacancy-item[href]"):
        href = link["href"]
        last_segment = href.rstrip("/").rsplit("/", 1)[-1]
        match = TRAILING_ID_RE.search(last_segment)
        # jobylon-v2 on HEMA's site also renders filter links (e.g. "/vacatures/winkel")
        # with the same a.vacancy-item-like markup elsewhere on the page in theory,
        # but real jobs always end with "-<numeric id>"; this skips those.
        if not match or match.group(1) in jobs:
            continue
        external_id = match.group(1)

        title_el = link.select_one("h3")
        location_el = link.select_one(".jobylon-v2.location .metadata-text")

        jobs[external_id] = {
            "source": source,
            "external_id": external_id,
            "title": title_el.get_text(strip=True) if title_el else None,
            "company": source,
            "location": location_el.get_text(strip=True) if location_el else None,
            "url": href if href.startswith("http") else "https://" + href.lstrip("/"),
            "description": None,
        }

    return list(jobs.values())


def fetch_live_search(base_url: str, source: str, limit: int = 1000) -> list[dict]:
    """
    Jobylon (v2 template, confirmed via the "jobylon-v2" CSS classes) renders
    jobs server-side in the HTML of the job overview page itself -- no
    separate JSON endpoint needed, no login. Pagination goes through query
    params "o" (offset) and "n" (per-page count, default 10 for HEMA);
    setting "n" higher than the total number of jobs (tested up to n=1000,
    ~860 results for HEMA in one request, ~380KB) fetches everything in a
    single GET instead of having to loop over ~86 pages.
    """
    resp = requests.get(
        base_url.rstrip("/"),
        params={"n": limit},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    resp.raise_for_status()
    return parse_search_results(resp.text, source)
