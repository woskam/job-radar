import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def parse_search_results(html: str, base_url: str, source: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs = []

    for link in soup.select("a.url[href^='/vacatures/']"):
        href = link.get("href")
        if not href:
            continue
        title = link.get("title") or link.get_text(strip=True)

        # Structure is consistent: the meta <ul> next to the title contains
        # [category, location, hours, (salary)] -- location is always at index 1.
        ul = link.parent.select_one("ul")
        items = [li.get_text(strip=True) for li in ul.select("li")] if ul else []
        location = items[1] if len(items) > 1 else None

        jobs.append({
            "source": source,
            "external_id": href,
            "title": title,
            "company": source,
            "location": location,
            "url": base_url.rstrip("/") + href,
            "description": None,
        })

    return jobs


def fetch_live_search(base_url: str, source: str) -> list[dict]:
    """
    VodafoneZiggo's careers site (Laravel/Livewire) renders the job list
    server-side at /vacatures, no login/API needed. No usable server-side
    keyword filter found, so same as Greenhouse/UWV: fetch everything,
    matching/scorer.py filters locally on our keywords.
    """
    resp = requests.get(
        f"{base_url.rstrip('/')}/vacatures",
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    return parse_search_results(resp.text, base_url, source)
