import json
import re

import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def _fetch_raw(handle: str) -> tuple[str, dict]:
    """
    GET join.com's public company page and return (slug, next_data) --
    join.com's own API requires a per-company token (not usable for bulk),
    but the company page itself server-renders the job list into an
    embedded Next.js `__NEXT_DATA__` block, no login needed.

    `handle` can be the numeric company id (Pegel Berlin's export uses
    these) or the slug directly -- join.com/companies/<numeric id> 301s to
    join.com/companies/<slug>, confirmed live, so either works. `slug` is
    read back from the final URL either way, since job detail URLs are
    built from the slug, not the numeric id.
    """
    resp = requests.get(
        f"https://join.com/companies/{handle}",
        headers={"User-Agent": USER_AGENT},
        timeout=15,
        allow_redirects=True,
    )
    resp.raise_for_status()
    slug = resp.url.rstrip("/").rsplit("/", 1)[-1]

    match = NEXT_DATA_RE.search(resp.text)
    if not match:
        raise ValueError("no __NEXT_DATA__ block found on join.com company page")
    return slug, json.loads(match.group(1))


def _jobs_state(next_data: dict) -> dict:
    return next_data.get("props", {}).get("pageProps", {}).get("initialState", {}).get("jobs", {})


def parse_search_results(next_data: dict, slug: str, source: str) -> list[dict]:
    jobs = []
    for item in _jobs_state(next_data).get("items", []):
        city = item.get("city") or {}
        if item.get("workplaceType") == "REMOTE" and not city.get("cityName"):
            location = "Remote" + (f" ({city['countryName']})" if city.get("countryName") else "")
        else:
            location = ", ".join(v for v in [city.get("cityName"), city.get("countryName")] if v) or None

        job_id = item.get("id")
        id_param = item.get("idParam")
        if job_id is None or not id_param:
            continue

        jobs.append({
            "source": source,
            "external_id": str(job_id),
            "title": item.get("title"),
            "company": source,
            "location": location,
            "url": f"https://join.com/companies/{slug}/{id_param}",
            "description": None,
        })
    return jobs


def parse_total(next_data: dict) -> int | None:
    """
    The embedded state's own pagination.total -- fetch_live_search only
    ever sees the first page (observed perPage=5 on the company page's
    initial server render; join.com's frontend fetches further pages from
    an undocumented GraphQL endpoint, candidate-api/graphql, not
    reverse-engineered here), so a tenant with more open roles than that
    page size is undercounted by len(jobs) alone -- same page-size-cap
    situation as Workday/Phenom/Oracle/Radancy elsewhere in this project.
    """
    return _jobs_state(next_data).get("pagination", {}).get("total")


def fetch_live_search(handle: str, source: str) -> list[dict]:
    """
    Only the first page of results (see parse_total's note) -- fine for
    scheduler.py's regular cycle (matching/scorer.py filters downstream
    anyway), but add_company.py's verifier reports the real total
    separately so a multi-page tenant isn't silently logged as fully
    covered.
    """
    slug, next_data = _fetch_raw(handle)
    return parse_search_results(next_data, slug, source)
