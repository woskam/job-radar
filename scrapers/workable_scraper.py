import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def parse_search_results(data: dict, source: str) -> list[dict]:
    jobs = []

    for posting in data.get("jobs", []):
        external_id = posting.get("shortcode")
        if not external_id:
            continue

        location = ", ".join(x for x in (posting.get("city"), posting.get("country")) if x) or None
        if not location and posting.get("telecommuting"):
            location = "Remote"

        jobs.append({
            "source": source,
            "external_id": external_id,
            "title": posting.get("title"),
            "company": source,
            "location": location,
            "url": posting.get("url") or f"https://apply.workable.com/j/{external_id}",
            "description": None,
        })

    return jobs


def fetch_live_search(handle: str, source: str) -> list[dict]:
    """
    Workable's public "widget" API is meant for embedding a company's full
    open-jobs list on its own site, so by design it returns everything in
    one GET call, no login needed, no keyword param (filtering on keywords
    happens downstream in matching/scorer.py). An empty `jobs: []` is a
    normal response (company currently has no open roles), not an error.

    `handle` is the account slug in the company's own
    https://apply.workable.com/{handle}/ careers site.
    """
    resp = requests.get(
        f"https://apply.workable.com/api/v1/widget/accounts/{handle}",
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    return parse_search_results(resp.json(), source)
