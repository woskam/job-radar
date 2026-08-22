import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def parse_search_results(data: dict, source: str) -> list[dict]:
    jobs = []

    for posting in data.get("jobs", []):
        jobs.append({
            "source": source,
            "external_id": posting["id"],
            "title": posting.get("title"),
            "company": source,
            "location": posting.get("location"),
            "url": posting.get("jobUrl"),
            # Ashby already includes the full job description in the listing
            # itself -- description_fetcher.py then skips a separate fetch.
            "description": posting.get("descriptionPlain"),
        })

    return jobs


def fetch_live_search(board_token: str, source: str) -> list[dict]:
    """
    Ashby's Job Board API is public and returns the full current job list in
    a single GET call, no login needed -- same as Greenhouse. No keyword
    param, so filtering on keywords happens downstream in matching/scorer.py.

    `board_token` is the last path segment of the jobs.ashbyhq.com/{token}
    URL (e.g. "mistral.ai" for Mistral).
    """
    resp = requests.get(
        f"https://api.ashbyhq.com/posting-api/job-board/{board_token}",
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    return parse_search_results(resp.json(), source)
