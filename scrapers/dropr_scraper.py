import re

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Every Dropr vacancy link carries both classes, has an "-e<digits>" job id
# suffix in its href, and repeats the clean title in data-track-value (so we
# don't need to worry about nested markup inside the link text). Confirmed on
# two different tenants (Action, ICI Paris XL) -- the surrounding class names
# (list-item__title vs list-ui__title etc.) differ per client theme, so we
# deliberately don't rely on those.
JOB_LINK_SELECTOR = "a.js-href.js-track[href]"
EXTERNAL_ID_RE = re.compile(r"-e(\d+)/?(?:\?.*)?$")


def parse_search_results(html: str, base_url: str, source: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs: dict[str, dict] = {}

    for link in soup.select(JOB_LINK_SELECTOR):
        href = link.get("href")
        match = EXTERNAL_ID_RE.search(href or "")
        if not match:
            continue
        external_id = match.group(1)
        if external_id in jobs:
            continue

        title = link.get("data-track-value") or link.get_text(strip=True)

        # Location is the first <li> in the <ul> that follows the <h3>
        # wrapping the link -- no reliable "location" class across tenants
        # (Action has list-item__meta-item--location, ICI Paris XL just has
        # plain list-ui__meta-item for both location and hours), but the
        # first meta item is location on both.
        location = None
        heading = link.find_parent("h3")
        meta_list = heading.find_next_sibling("ul") if heading else None
        if meta_list:
            first_item = meta_list.find("li")
            if first_item:
                location = first_item.get_text(strip=True)

        jobs[external_id] = {
            "source": source,
            "external_id": external_id,
            "title": title,
            "company": source,
            "location": location,
            "url": href if href.startswith("http") else base_url.rstrip("/") + href,
            "description": None,
        }

    return list(jobs.values())


def fetch_live_search(base_url: str, source: str, keywords: str = "") -> list[dict]:
    """
    Dropr (dropr.io) career sites render search results server-side at
    <base_url>?q=<keywords> -- no login needed, confirmed for Action
    (nl.action.jobs/vacatures/kantoor) and ICI Paris XL
    (werkenbijiciparisxl.nl/vacatures). No pagination loop -- like the other
    scrapers here, one request per keyword is enough given the keyword list
    already narrows things down.
    """
    resp = requests.get(
        base_url,
        params={"q": keywords},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    return parse_search_results(resp.text, base_url, source)
