import re

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
PAGE_SIZE = 20  # cards per page, confirmed against werkenbij.amsterdam.nl
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def parse_search_results(html: str, base_url: str, source: str) -> list[dict]:
    """
    City of Amsterdam's werkenbij.amsterdam.nl runs on a custom ASP.NET/Razor
    Pages CMS (no known ATS) with server-side rendered search results on
    /vacatures -- no separate JSON endpoint found. The nav search bar posts
    to /zoeken, but that's a site-wide content search (0 job cards for a job
    keyword) -- the actual job filter is the separate filter form on
    /vacatures itself (name="Keywords", GET) -- confirmed:
    /vacatures?Keywords=jurist returned 13 of the 43 cards instead of all 43.
    Each card is a <div class="card"> with no stable numeric ID; the URL does
    contain a UUID as the last part of the slug (e.g.
    "...-f0f7b47c-4536-429a-8364-10457d882a37") which serves as external_id.
    NOTE: the UUID itself contains hyphens, so simply splitting on the last
    "-" only grabs the last chunk -- hence a regex match on the full UUID
    pattern.
    No location field per card (only sector/hours/education/salary) -- all
    jobs are in practice at the City of Amsterdam, so location=None, same as
    the other scrapers when a clean location field is missing.
    """
    soup = BeautifulSoup(html, "lxml")
    jobs = []

    for card in soup.select("div.card"):
        link = card.select_one(".card-title a")
        if not link:
            continue

        href = link.get("href") or ""
        match = UUID_RE.search(href.rstrip("/"))
        external_id = match.group(0) if match else None
        if not external_id:
            continue

        jobs.append({
            "source": source,
            "external_id": external_id,
            "title": link.get_text(strip=True),
            "company": source,
            # No separate location field per card, but this is the municipality's
            # own job site -- virtually all jobs are in Amsterdam.
            "location": "Amsterdam",
            "url": href if href.startswith("http") else base_url.rstrip("/") + href,
            "description": None,
        })

    return jobs


def fetch_live_search(base_url: str, source: str, keywords: str = "") -> list[dict]:
    """
    GET {base_url}/vacatures?Keywords=<keywords>&pageNumber=<n> -- no login
    needed. Server-side paginated, 20 cards per page (tested against
    werkenbij.amsterdam.nl: 43 results in total across 3 pages of 20/20/3).
    We keep going until a page returns fewer than PAGE_SIZE cards.
    """
    session = requests.Session()
    all_jobs: list[dict] = []
    page = 1

    while True:
        resp = session.get(
            f"{base_url.rstrip('/')}/vacatures",
            params={"Keywords": keywords, "pageNumber": page},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        page_jobs = parse_search_results(resp.text, base_url, source)
        if not page_jobs:
            break

        all_jobs.extend(page_jobs)
        if len(page_jobs) < PAGE_SIZE:
            break
        page += 1

    # dedupe: the same job could in theory appear on multiple pages if the
    # result set shifts between requests
    seen = set()
    deduped = []
    for job in all_jobs:
        if job["external_id"] in seen:
            continue
        seen.add(job["external_id"])
        deduped.append(job)

    return deduped
