import re

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
SLUG_RE = re.compile(r"[^a-z0-9]+")
JOBOFFER_ID_RE = re.compile(r"joboffer/([a-f0-9-]{36})")


def _slugify(name: str) -> str:
    return SLUG_RE.sub("-", (name or "").lower()).strip("-")


def parse_search_results(html: str, base_url: str, source: str) -> list[dict]:
    """
    TSF (tsf.nl) is an Angular SSR job platform used by the province of
    Noord-Holland (and presumably more government clients, recognizable by
    "Powered by TSF" in the footer). The /vacatures page is server-side
    rendered (Angular Universal) and contains all open jobs directly in the
    HTML -- no separate JSON endpoint found (main-*.js contains no literal
    /api/ paths; apiEndpoint is injected at runtime). Cards use NO <a href>,
    but a JS-routed <div role="link">, so the detail URL isn't directly
    present. Each card does, however, contain a background image
    "cdn.tsf.nl/.../joboffer/{uuid}/..." whose UUID exactly matches the last
    path segment of the real detail URL (confirmed against sitemap.xml). The
    slug before it (first path segment) is ignored by the Angular router --
    tested with a deliberately wrong slug, which just returned HTTP 200 --
    so we build it ourselves from the title for a clean URL.
    """
    soup = BeautifulSoup(html, "lxml")
    jobs = []

    for item in soup.select("app-vacature-item"):
        title_el = item.select_one(".kaart__titel")
        title = title_el.get_text(strip=True) if title_el else None

        header = item.select_one(".kaart__header")
        style = header.get("style", "") if header else ""
        match = JOBOFFER_ID_RE.search(style)
        if not match:
            continue
        external_id = match.group(1)

        location = None
        loc_icon = item.find("mat-icon", attrs={"aria-label": "standplaats"})
        if loc_icon:
            li = loc_icon.find_parent("li")
            loc_p = li.select_one("p") if li else None
            location = loc_p.get_text(strip=True) if loc_p else None

        jobs.append({
            "source": source,
            "external_id": external_id,
            "title": title,
            "company": source,
            "location": location,
            "url": f"{base_url.rstrip('/')}/vacatures/{_slugify(title)}/{external_id}",
            "description": None,
        })

    return jobs


def fetch_live_search(base_url: str, source: str, keywords: str = "") -> list[dict]:
    """
    GET {base_url}/vacatures -- no login needed. Server-renders all open jobs
    directly in the HTML (confirmed against the province of Noord-Holland:
    15 jobs on the page, exactly matching the number of <loc> entries in
    sitemap.xml, so no client-side pagination we'd be missing). Various
    query-string variants for keyword filtering (zoekterm/trefwoord/q/
    keyword/zoekwoord, pagina/page/pageNumber/offset) all returned identical,
    unfiltered results -- the search bar apparently uses an Angular-specific
    query-string encoding that couldn't be reproduced with simple GET params.
    Hence: always fetch the full list and filter `keywords` (if given)
    client-side on title, same as with Recruitee.
    """
    resp = requests.get(
        f"{base_url.rstrip('/')}/vacatures",
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    jobs = parse_search_results(resp.text, base_url, source)

    if keywords:
        kw = keywords.lower()
        jobs = [j for j in jobs if kw in (j["title"] or "").lower()]

    return jobs
