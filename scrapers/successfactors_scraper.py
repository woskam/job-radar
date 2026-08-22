import re

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
            "url": base_url.rstrip("/") + href,
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


def fetch_live_search(base_url: str, source: str, keywords: str = "") -> list[dict]:
    """
    Automatically detects which SF Career Site Builder template a company
    uses (old: server-side HTML, new: JSON API) and parses accordingly.
    No login needed -- public job search, same as Workday. `keywords`
    filters server-side on the search term, same as the Workday scraper.
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
        return parse_new_template(data, base_url, source)

    return parse_old_template(resp.text, base_url, source)
