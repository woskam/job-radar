import re
from urllib.parse import urlparse

import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _guess_locale(base_url: str) -> str:
    # Phenom career URLs are structured as https://{host}/{country}/{lang}/...
    # (e.g. "/us/en", "/nl/nl") -- the widgets call expects a "lang" field as
    # "{lang}_{country}" (e.g. "en_us"). Purely cosmetic/for logging on
    # Phenom's side (see the fetch_live_search docstring); if the pattern
    # isn't recognized, we fall back to "en_us".
    parts = [p for p in urlparse(base_url).path.split("/") if p]
    if len(parts) >= 2 and re.fullmatch(r"[a-z]{2}", parts[0]) and re.fullmatch(r"[a-z]{2}", parts[1]):
        country, lang = parts[0], parts[1]
        return f"{lang}_{country}"
    return "en_us"


def parse_search_results(data: dict, base_url: str, source: str) -> list[dict]:
    jobs = []
    base = base_url.rstrip("/")

    for job in data.get("refineSearch", {}).get("data", {}).get("jobs", []):
        job_id = job.get("jobId")
        if not job_id:
            continue

        jobs.append({
            "source": source,
            "external_id": job_id,
            "title": job.get("title"),
            "company": source,
            "location": job.get("location"),
            "url": f"{base}/job/{job_id}",
            "description": None,
        })

    return jobs


def fetch_live_search(base_url: str, source: str, keywords: str = "", limit: int = 20, offset: int = 0) -> list[dict]:
    """
    Phenom (CareerConnect) career sites load their search results via a public
    POST to "https://{host}/widgets" with ddoKey "refineSearch" -- no login
    needed, this is exactly the call the search-results page itself makes
    too. Discovered by searching the HTML for the embedded "phApp" config
    (var phApp = phApp || {...}) where "widgetApiEndpoint" points at this URL.

    Confirmed at eBay (jobs.ebayinc.com), de Volksbank (werkenbij.devolksbank.nl)
    and Mars Benelux (careers.mars.com, search/listing layer only -- the
    application form runs separately on Workday).

    Important: "refNum" (the tenant code, e.g. "EBAEBAUS") does NOT need to
    be sent -- tested with it omitted and even with a deliberately wrong
    refNum, both gave identical results. The tenant is determined purely via
    the request's Host header, so base_url (including host) is sufficient,
    unlike Workday where tenant+site are explicitly required.

    `base_url` is the locale-specific career root as used in fetch_live_search
    for job URLs, e.g. "https://jobs.ebayinc.com/us/en" -- NO
    "/search-results" suffix. `keywords` filters server-side (empty = all
    jobs); empty vs. a nonsense keyword tested and gave all and 0 results
    respectively, so 0 search results returns a clean empty jobs list (no
    separate template detection needed like with SuccessFactors).
    """
    parsed = urlparse(base_url)
    widgets_url = f"{parsed.scheme}://{parsed.netloc}/widgets"

    response = requests.post(
        widgets_url,
        json={
            "ddoKey": "refineSearch",
            "lang": _guess_locale(base_url),
            "deviceType": "desktop",
            "pageName": "search-results",
            "size": limit,
            "from": offset,
            "jobs": True,
            "keywords": keywords,
        },
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        timeout=15,
    )
    response.raise_for_status()
    return parse_search_results(response.json(), base_url, source)
