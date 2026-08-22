import re
import time

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
BASE_URL = "https://www.werkenvoornederland.nl"
PAGE_SIZE = 20  # cards per page, confirmed against /vacatures

# The landing page and /zoeken itself do NOT contain server-side rendered
# job postings (SPA-like screen that waits on JS). The underlying CMS is
# Hippo/BloomReach (recognizable by data-govan-* attributes and the
# "_hn:type=component-rendering&_hn:ref=..." Hippo Site Toolkit
# async-component mechanism). Confirmed via curl: the /vacatures page contains
# a <div id="/vacatures?_hn:type=component-rendering&_hn:ref=rXX_rX_rX"
# class="{letter}{NNN}Async"> right before the job-list container -- the
# class-prefix letter (observed: b/d/e/g/...) differs per request cycle
# (depends on a per-render JS namespace counter), so do NOT hardcode it to
# "d". That same URL (fetched standalone, with "&amp;" unescaped to "&")
# returns an HTML fragment WITH the server-side rendered job cards -- no
# login needed. This "ref" itself turned out to be stable in practice across
# repeated requests, but we still look it up dynamically instead of
# hardcoding it, in case it changes per deploy.
REF_RE = re.compile(
    r'/vacatures\?_hn:type=component-rendering&amp;_hn:ref=(\w+)"\s+class="[a-z]\d+Async"'
)


def _discover_results_ref(html: str, session: requests.Session, headers: dict) -> str:
    """
    Among the candidate refs on the /vacatures page (there are usually 2: one
    for the job list, one for "saved jobs" which is always empty), find the
    ref that actually returns job cards.
    """
    candidates = REF_RE.findall(html)
    if not candidates:
        raise RuntimeError(
            "werkenvoornederland.nl: no Hippo component-rendering ref "
            "found on /vacatures -- page structure has likely changed."
        )

    for ref in candidates:
        resp = session.get(
            f"{BASE_URL}/vacatures",
            params={"_hn:type": "component-rendering", "_hn:ref": ref},
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        if 'data-govan-component="search-result-item"' in resp.text:
            return ref

    raise RuntimeError(
        "werkenvoornederland.nl: none of the found refs returned job cards."
    )


def parse_search_results(html: str, source: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs = []

    for item in soup.select('li[data-govan-component="search-result-item"]'):
        section = item.select_one("section.vacancy")
        title_link = item.select_one("h2.vacancy__title a")
        if title_link is None:
            continue

        href = title_link.get("href") or ""
        url = href if href.startswith("http") else f"{BASE_URL}{href}"

        external_id = (section.get("data-baanpleinid") if section else None) or href.rsplit("/", 1)[-1]

        employer = item.select_one("p.vacancy__employer")
        company = employer.get_text(strip=True) if employer else None

        location = None
        loc_icon = item.select_one("span.ro_icon-locatiemarker")
        if loc_icon is not None:
            li = loc_icon.find_parent("li")
            value = li.select_one(".job-short-info__value") if li else None
            if value is not None:
                location = re.sub(r"\s+", " ", value.get_text(" ", strip=True)) or None

        jobs.append({
            "source": source,
            "external_id": str(external_id),
            "title": title_link.get_text(strip=True),
            "company": company,
            "location": location,
            "url": url,
            "description": None,
        })

    return jobs


def fetch_live_search(
    term: str,
    source: str,
    employer_match: str | None = None,
    max_pages: int = 10,
) -> list[dict]:
    """
    werkenvoornederland.nl is THE central job portal for the Dutch central
    government (ministries + many executive agencies). Confirmed working as
    a public, login-free full-text search via the Hippo/BloomReach
    "component-rendering" AJAX endpoint (see _discover_results_ref above).
    Tested with term="MIVD" (47 results, employer "Militaire Inlichtingen-
    en Veiligheidsdienst (MIVD)") and term="Rijkswaterstaat"/
    "Belastingdienst"/"Douane"/"DUO"/"AIVD" -- all confirmed present.

    `term` is a free-text search query (query param "term") that matches
    both title/description and (presumably) organization name -- so fuzzy,
    not an exact employer filter (there is NO separate organization facet on
    this site, only field/employment type/location/salary/job type/date).
    So for a specific government organization ALWAYS also pass
    `employer_match`: a standalone, case-insensitive substring that must
    appear in the scraped employer field (job["company"]), to filter out
    fuzzy matches on other organizations. Example: AIVD's employer field is
    literally "Algemene Inlichtingen- en Veiligheidsdienst" (does NOT contain
    the bare letters "AIVD"), so call with term="AIVD",
    employer_match="Algemene Inlichtingen- en Veiligheidsdienst". For MIVD,
    conversely, use employer_match="Militaire Inlichtingen" (otherwise
    "Inlichtingen- en Veiligheidsdienst" matches both).

    Pagination via query param "pagina" (1-indexed), 20 results per page --
    confirmed against term="UWV" (3 pages tested, each with 20 unique
    results). `max_pages` caps the number of pages fetched.
    """
    session = requests.Session()
    headers = {"User-Agent": USER_AGENT}

    # werkenvoornederland.nl's robots.txt allows "Request-rate: 10/1";
    # ref-discovery turned out in practice to sometimes return an empty/odd
    # response when requests follow each other too quickly (transient) --
    # one retry after a short pause fixes that.
    try:
        base_resp = session.get(f"{BASE_URL}/vacatures", headers=headers, timeout=15)
        base_resp.raise_for_status()
        ref = _discover_results_ref(base_resp.text, session, headers)
    except RuntimeError:
        time.sleep(1.0)
        base_resp = session.get(f"{BASE_URL}/vacatures", headers=headers, timeout=15)
        base_resp.raise_for_status()
        ref = _discover_results_ref(base_resp.text, session, headers)

    all_jobs: list[dict] = []
    seen_ids: set[str] = set()

    for page in range(1, max_pages + 1):
        if page > 1:
            time.sleep(0.3)
        resp = session.get(
            f"{BASE_URL}/vacatures",
            params={
                "_hn:type": "component-rendering",
                "_hn:ref": ref,
                "term": term,
                "pagina": page,
            },
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        jobs = parse_search_results(resp.text, source)
        if not jobs:
            break

        new_jobs = [j for j in jobs if j["external_id"] not in seen_ids]
        if not new_jobs:
            break
        seen_ids.update(j["external_id"] for j in new_jobs)
        all_jobs.extend(new_jobs)

        if len(jobs) < PAGE_SIZE:
            break  # last page

    if employer_match:
        needle = employer_match.lower()
        all_jobs = [j for j in all_jobs if needle in (j["company"] or "").lower()]

    return all_jobs
