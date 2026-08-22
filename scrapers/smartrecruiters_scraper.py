import re

import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
SLUG_RE = re.compile(r"[^a-z0-9]+")
MAX_PAGE_SIZE = 100  # the API silently ignores a higher limit value and caps at 100


def _slugify(name: str) -> str:
    # SmartRecruiters' public postingUrl follows the pattern "{id}-{slug}",
    # with slug = lowercase title, non-alphanumeric replaced by a hyphen
    # (verified against the posting-detail endpoint, e.g. "Technician" ->
    # "technician"). The list endpoint (/postings) doesn't itself return a
    # public URL (only "ref", an API URL) -- hence we build it ourselves here
    # instead of making an extra detail call per job.
    return SLUG_RE.sub("-", name.lower()).strip("-")


def parse_search_results(data: dict, source: str, company_id: str | None = None) -> list[dict]:
    # The public job URL uses company_id (the exact, case-sensitive path
    # segment from the careers URL, e.g. "wehkamp"), not necessarily `source`
    # (our own display name, which may be capitalized differently, e.g. "Wehkamp").
    url_slug = company_id or source
    jobs = []

    for posting in data.get("content", []):
        posting_id = posting["id"]
        title = posting.get("name") or ""
        location = posting.get("location") or {}

        jobs.append({
            "source": source,
            "external_id": posting_id,
            "title": title,
            "company": source,
            "location": location.get("fullLocation"),
            "url": f"https://jobs.smartrecruiters.com/{url_slug}/{posting_id}-{_slugify(title)}",
            "description": None,
        })

    return jobs


def fetch_live_search(company_id: str, source: str, keywords: str = "") -> list[dict]:
    """
    SmartRecruiters' Posting API
    (https://api.smartrecruiters.com/v1/companies/{companyId}/postings) is
    public and requires no authentication -- just a GET like any visitor
    sees on the careers page. `company_id` is the identifier as it appears
    in the careers URL (e.g. "ASICS", "wehkamp"). Pagination via
    offset/limit, max 100 results per page regardless of a higher limit
    value, so we keep going until all pages are exhausted.
    """
    session = requests.Session()
    all_postings: list[dict] = []
    offset = 0

    while True:
        resp = session.get(
            f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings",
            params={"q": keywords, "offset": offset, "limit": MAX_PAGE_SIZE},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        page = data.get("content", [])
        all_postings.extend(page)

        offset += len(page)
        if not page or offset >= data.get("totalFound", 0):
            break

    return parse_search_results({"content": all_postings}, source, company_id=company_id)
