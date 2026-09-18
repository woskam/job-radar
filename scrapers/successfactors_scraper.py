import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

CSRF_RE = re.compile(r'var CSRFToken\s*=\s*"([^"]+)"')
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _find_nearby_location(link_tag) -> str | None:
    # Layout differs per company (table for C&A/MediaMarkt, "tile" divs for
    # Under Armour) -- walk up to the nearest ancestor that contains a
    # .jobLocation, instead of assuming a fixed tr/td structure.
    node = link_tag
    for _ in range(8):
        node = node.parent
        if node is None:
            break
        location_el = node.select_one(".jobLocation, .section-field.location")
        if location_el:
            # In the .section-field.location variant (e.g. Under Armour) there's
            # a "Location" label span before the value -- grab specifically the
            # value if it's findable as a separate element, otherwise the whole text.
            value_el = location_el.select_one('[id$="-value"]')
            return (value_el or location_el).get_text(strip=True)
    return None


def parse_old_template(html: str, base_url: str, source: str) -> list[dict]:
    """Older, fully server-side rendered SF Career Site Builder (j2w) sites,
    e.g. C&A, MediaMarkt NL, Under Armour -- the jobs are already in the
    /search HTML itself (desktop/mobile variants return the same link twice,
    hence dedupe on external_id)."""
    soup = BeautifulSoup(html, "lxml")
    jobs: dict[str, dict] = {}

    for link in soup.select("a.jobTitle-link[href]"):
        href = link["href"]
        external_id = href.rstrip("/").rsplit("/", 1)[-1]
        if external_id in jobs:
            continue

        jobs[external_id] = {
            "source": source,
            "external_id": external_id,
            "title": link.get_text(strip=True),
            "company": source,
            "location": _find_nearby_location(link),
            # href is root-relative (e.g. "/ey/job/...") and, for a tenant
            # whose base_url itself has a path segment (e.g. EY's ".../ey"),
            # already repeats it -- naive string concatenation used to
            # produce a broken double-segment URL ("/ey/ey/job/...", 404).
            # urljoin resolves a root-relative href against just the base's
            # scheme+host, same as a browser would, so it can't duplicate.
            "url": urljoin(base_url, href),
            "description": None,
        }

    return list(jobs.values())


def parse_new_template(data: dict, base_url: str, source: str) -> list[dict]:
    """Newer "Recruiting Marketing" SF Career Site Builder sites, e.g. Triodos --
    jobs come through a JSON API (see fetch_new_template)."""
    jobs = []

    for entry in data.get("jobSearchResult", []):
        r = entry["response"]
        location = ", ".join(loc.strip() for loc in r.get("jobLocationShort", []) if loc.strip())

        jobs.append({
            "source": source,
            "external_id": r["id"],
            "title": r.get("unifiedStandardTitle"),
            "company": source,
            "location": location or None,
            "url": f"{base_url.rstrip('/')}/job/{r.get('urlTitle')}/{r['id']}-en_US",
            "description": None,
        })

    return jobs


def fetch_new_template(
    session: requests.Session, base_url: str, search_url: str, keywords: str = "", page: int = 0
) -> dict:
    resp = session.get(search_url, timeout=15, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()

    match = CSRF_RE.search(resp.text)
    if not match:
        raise RuntimeError(f"No CSRFToken found at {search_url} -- unknown SF template")

    api_resp = session.post(
        f"{base_url.rstrip('/')}/services/recruiting/v1/jobs",
        json={
            "locale": "en_US", "pageNumber": page, "sortBy": "", "keywords": keywords,
            "location": "", "facetFilters": {}, "brand": "", "skills": [],
            "categoryId": 0, "alertId": "", "rcmCandidateId": "",
        },
        headers={
            "X-CSRF-Token": match.group(1),
            "Content-Type": "application/json",
            "Referer": search_url,
            "User-Agent": USER_AGENT,
        },
        timeout=15,
    )
    api_resp.raise_for_status()
    return api_resp.json()


def _search(base_url: str, source: str, keywords: str = "") -> tuple[list[dict], int | None]:
    """
    Shared by fetch_live_search and add_company.py's verifier. Automatically
    detects which SF Career Site Builder template a company uses (old:
    server-side HTML, new: JSON API) and parses accordingly. No login
    needed -- public job search, same as Workday. `keywords` filters
    server-side on the search term, same as the Workday scraper.

    Returns (jobs, total). For the newer JSON-API template, `total` is
    data["totalJobs"] -- the tenant's real total, not just this page's
    length: fetch_new_template only ever asks for pageNumber=0, so (like
    Workday/Phenom) a tenant with more than one page of results would
    otherwise be undercounted (found live: Triodos Bank reports
    totalJobs=21 but this single call alone returns 10). The older, fully
    server-side rendered template has no separate "total" concept -- every
    job is already in the /search HTML itself -- so total is always None
    there and len(jobs) IS the real total.
    """
    session = requests.Session()
    search_url = f"{base_url.rstrip('/')}/search?q={keywords}&locationsearch="

    resp = session.get(search_url, timeout=15, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()

    # Detection based on the presence of the new-template marker (CSRFToken),
    # not on whether jobs happen to already be in the HTML -- with 0 search
    # results on an old-template site there's likewise no "jobTitle-link" on
    # the page.
    if CSRF_RE.search(resp.text):
        data = fetch_new_template(session, base_url, search_url, keywords=keywords)
        return parse_new_template(data, base_url, source), data.get("totalJobs")

    return parse_old_template(resp.text, base_url, source), None


def fetch_live_search(base_url: str, source: str, keywords: str = "") -> list[dict]:
    """
    See _search for the template-detection/total-count details. This wraps
    it and returns just the parsed job list -- NOTE: for new-template
    tenants only page 1 is fetched, no loop over the real total (see
    _search's docstring); a broad/no-keyword search against a large
    new-template tenant can silently miss postings past this page in
    scheduler.py's production scrape.
    """
    jobs, _ = _search(base_url, source, keywords=keywords)
    return jobs
