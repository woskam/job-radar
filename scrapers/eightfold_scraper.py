import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
PAGE_SIZE = 10  # Eightfold's public API always caps `num` at 10, regardless of what you request


def parse_search_results(data: dict, base_url: str, source: str) -> list[dict]:
    jobs = []

    for position in data.get("positions", []):
        external_id = str(position["id"])

        jobs.append({
            "source": source,
            "external_id": external_id,
            "title": position.get("name"),
            "company": source,
            "location": position.get("location"),
            "url": position.get("canonicalPositionUrl") or f"{base_url.rstrip('/')}/careers/job/{external_id}",
            "description": None,
        })

    return jobs


def fetch_live_search(
    base_url: str, domain: str, source: str, query: str = "", location: str = "", limit: int = 100
) -> list[dict]:
    """
    Eightfold AI has a public JSON API at /api/apply/v2/jobs, no login
    needed -- just the job search every visitor sees.

    `base_url` is the host the careers site runs on: can be a custom domain
    (e.g. explore.jobs.netflix.net) or an *.eightfold.ai subdomain (e.g.
    portal.careers.hsbc.com / hsbc.eightfold.ai -- both work, same tenant).
    `domain` is Eightfold's internal "group id", found in the careers HTML
    as `window._EF_GROUP_ID = "..."` (e.g. "netflix.com", "hsbc.com") --
    NOTE: the site subdomain name is not a reliable guess for this group id
    (aexp.eightfold.ai, for instance, runs under "aexp.com", not under the
    subdomain name itself), so always check the HTML source before adding a
    new company.

    If the group id no longer exists on this tenant, Eightfold returns a
    "Group ID not found" page with HTTP 404 -- raise_for_status() just lets
    that blow up, that's then a dead/migrated account, not a bug here.

    The API ignores a higher `num` and caps itself at 10 results per page,
    so we paginate via `start` until nothing more comes back, `count` is
    reached, or `limit` is reached.
    """
    session = requests.Session()
    jobs: dict[str, dict] = {}
    start = 0

    while len(jobs) < limit:
        resp = session.get(
            f"{base_url.rstrip('/')}/api/apply/v2/jobs",
            params={"domain": domain, "query": query, "location": location, "start": start, "num": PAGE_SIZE},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        page_jobs = parse_search_results(data, base_url, source)
        if not page_jobs:
            break

        for job in page_jobs:
            jobs[job["external_id"]] = job

        start += PAGE_SIZE
        if start >= data.get("count", 0):
            break

    return list(jobs.values())[:limit]
