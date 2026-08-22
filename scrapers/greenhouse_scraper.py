import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def parse_search_results(data: dict, source: str) -> list[dict]:
    jobs = []

    for posting in data.get("jobs", []):
        location = posting.get("location") or {}

        jobs.append({
            "source": source,
            "external_id": str(posting["id"]),
            "title": posting.get("title"),
            "company": source,
            "location": location.get("name"),
            "url": posting.get("absolute_url"),
            "description": None,
        })

    return jobs


def fetch_live_search(board_token: str, source: str) -> list[dict]:
    """
    Greenhouse's Job Board API is public and documented, no login needed:
    https://developers.greenhouse.io/job-board.html -- returns a company's
    full current job list in a single GET call (no keyword param, so
    filtering on keywords happens downstream in matching/scorer.py, same as
    with the Greenhouse listing bol.com itself shows on careers.bol.com).

    `board_token` is NOT necessarily the company name in lowercase -- for
    bol.com, for example, it's "bolcom" (not "bol"), tested and confirmed via
    curl. Look it up by trying a few variants against this endpoint, or check
    the network tab of the apply flow on the careers page (bol.com's own
    frontend is custom-built, Greenhouse only sits "behind" it for
    application processing, which is why the board_token doesn't appear
    literally in careers.bol.com's HTML).
    """
    resp = requests.get(
        f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs",
        params={"content": "true"},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    return parse_search_results(resp.json(), source)
