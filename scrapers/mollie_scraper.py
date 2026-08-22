import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def parse_search_results(html: str, base_url: str, source: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs: dict[str, dict] = {}

    for link in soup.select('a[href*="/vacancies/"]'):
        href = link.get("href")
        if not href or href in jobs:
            continue

        # Mollie's careers site is built with Framer (no-code site builder) --
        # no semantic class names, so read positionally: the card is always
        # [title, location, team, employment type] as separate text blocks.
        texts = [p.get_text(strip=True) for p in link.select("p.framer-text")]
        if not texts:
            continue
        title = texts[0]
        location = texts[1] if len(texts) > 1 else None

        jobs[href] = {
            "source": source,
            "external_id": href.rsplit("/", 1)[-1],
            "title": title,
            "company": source,
            "location": location,
            "url": base_url.rstrip("/") + "/" + href.lstrip("./"),
            "description": None,
        }

    return list(jobs.values())


def fetch_live_search(base_url: str, source: str) -> list[dict]:
    """
    Mollie's careers site (jobs.mollie.com) is built with Framer and renders
    open jobs server-side on the main page, no login/API needed. No
    server-side keyword filter found, so same as Greenhouse/UWV: fetch
    everything, matching/scorer.py filters locally.
    """
    resp = requests.get(
        base_url,
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    return parse_search_results(resp.text, base_url, source)
