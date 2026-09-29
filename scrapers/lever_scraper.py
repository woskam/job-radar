import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def parse_search_results(data: list[dict], handle: str, source: str) -> list[dict]:
    jobs = []

    for posting in data:
        external_id = posting.get("id")
        if not external_id:
            continue

        categories = posting.get("categories") or {}
        location = categories.get("location") or ", ".join(categories.get("allLocations") or []) or None

        jobs.append({
            "source": source,
            "external_id": external_id,
            "title": posting.get("text"),
            "company": source,
            "location": location,
            "url": posting.get("hostedUrl") or f"https://jobs.lever.co/{handle}/{external_id}",
            # Lever's descriptionPlain/opening fields are large HTML-derived
            # blobs -- None here, same as Ashby's siblings that skip it.
            "description": None,
        })

    return jobs


def fetch_live_search(handle: str, source: str) -> list[dict]:
    """
    Lever's public Postings API (github.com/lever/postings-api) is
    documented and needs no login -- returns a company's full current job
    list in a single GET call, no keyword param, same shape as Ashby/
    Greenhouse (filtering on keywords happens downstream in
    matching/scorer.py). Confirmed live: no pagination cap, a 170-posting
    company came back complete in one call.

    `handle` is the path segment in the company's own
    https://jobs.lever.co/{handle} careers site.
    """
    resp = requests.get(
        f"https://api.lever.co/v0/postings/{handle}",
        params={"mode": "json"},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    return parse_search_results(resp.json(), handle, source)
