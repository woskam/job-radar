import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
LOCATION_SELECTOR = ".job-location, .sr-job-location, .job-list__location"
TITLE_SELECTOR = ".job-list__title"


def _find_nearby_location(link_tag) -> str | None:
    # Radancy/TalentBrew tenants use different CSS classes AND structure per
    # site: ING/Citi nest the location in a separate ancestor section (walk
    # up), IKEA instead nests it AS a child within the same <a> -- look there
    # first, otherwise walk up (same approach as the SuccessFactors scraper).
    nested = link_tag.select_one(LOCATION_SELECTOR)
    if nested:
        return nested.get_text(strip=True)

    node = link_tag
    for _ in range(8):
        node = node.parent
        if node is None:
            break
        location_el = node.select_one(LOCATION_SELECTOR)
        if location_el:
            return location_el.get_text(strip=True)
    return None


def parse_search_results(html: str, base_url: str, source: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs: dict[str, dict] = {}

    for link in soup.select("a[data-job-id]"):
        external_id = link.get("data-job-id")
        href = link.get("href")
        if not external_id or not href or external_id in jobs:
            continue

        # Some tenants (IKEA) have title, location, category, and type all as
        # separate <span>s within the same <a> -- link.get_text() would then
        # glue everything together. Use the specific title element if it
        # exists, otherwise (ING/Citi: the <a> text is already just the
        # title) fall back to the plain approach.
        title_el = link.select_one(TITLE_SELECTOR)
        title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)

        jobs[external_id] = {
            "source": source,
            "external_id": external_id,
            "title": title,
            "company": source,
            "location": _find_nearby_location(link),
            "url": href if href.startswith("http") else base_url.rstrip("/") + href,
            "description": None,
        }

    return list(jobs.values())


def fetch_live_search(base_url: str, source: str, keywords: str = "", location: str = "", path: str = "search-jobs") -> list[dict]:
    """
    Radancy/TalentBrew career sites render search results server-side at
    /search-jobs?k=<keywords>&l=<location> -- no login needed. Not every
    TalentBrew tenant does this (IKEA's instance renders client-side via an
    AJAX call that couldn't be reproduced without devtools); check this per
    new company before adding it to companies.yaml.

    The `l=<location>` param isn't reliably honored by every tenant -- Citi's
    (jobs.citi.com) silently ignores it and returns unfiltered global results.
    For tenants like that, pass a tenant-specific pre-filtered `path` (e.g.
    Citi's "location/netherlands-jobs/287/2750405/2", found via the tenant's
    own site navigation) instead -- it's fetched directly with no k/l params,
    since it's already scoped, and parsed with the same parse_search_results.
    """
    if path != "search-jobs":
        resp = requests.get(
            f"{base_url.rstrip('/')}/{path.lstrip('/')}",
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
    else:
        resp = requests.get(
            f"{base_url.rstrip('/')}/search-jobs",
            params={"k": keywords, "l": location},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
    resp.raise_for_status()
    return parse_search_results(resp.text, base_url, source)
