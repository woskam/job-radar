import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def parse_search_results(data: dict, source: str) -> list[dict]:
    jobs = []

    for item in data.get("items", []):
        external_id = item.get("id")
        if not external_id:
            continue

        job_posting = item.get("_jobposting") or {}
        locations = job_posting.get("jobLocation") or []
        location = ", ".join(
            address["addressLocality"]
            for place in locations
            if (address := place.get("address")) and address.get("addressLocality")
        ) or None

        jobs.append({
            "source": source,
            "external_id": external_id,
            "title": item.get("title"),
            "company": source,
            "location": location,
            "url": item.get("url"),
            "description": None,
        })

    return jobs


def fetch_live_search(handle: str, source: str) -> list[dict]:
    """
    Teamtailor exposes a public JSON Feed 1.1 (jsonfeed.org) of a company's
    open jobs, no login needed, returned complete in a single GET call, no
    keyword param (filtering happens downstream in matching/scorer.py).
    Confirmed live: no pagination cap seen, a 73-posting company came back
    complete in one call, though the JSON Feed spec does support a
    `next_url` field for pagination in principle -- not handled here since
    it never appeared in testing.

    `handle` is the subdomain in the company's own
    https://{handle}.teamtailor.com careers site.
    """
    resp = requests.get(
        f"https://{handle}.teamtailor.com/jobs.json",
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    return parse_search_results(resp.json(), source)
