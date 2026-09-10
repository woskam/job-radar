import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def parse_search_results(data: dict, host: str, site_number: str, source: str) -> list[dict]:
    """
    `data` is the raw JSON from recruitingCEJobRequisitions. The API wraps
    the result in items[0] (there's always exactly 1 "search" object per
    call, even with 0 hits) -- hence the guard on an empty items list
    instead of assuming items[0] exists.
    """
    items = data.get("items") or []
    if not items:
        return []

    jobs = []
    for req in items[0].get("requisitionList", []):
        # For multi-location jobs, Oracle returns secondaryLocations in addition
        # to PrimaryLocation (requested via expand=...secondaryLocations in
        # fetch_live_search) -- merge all location names so the scorer can see
        # an Amsterdam match even if it isn't the primary location.
        locations = [req["PrimaryLocation"]] if req.get("PrimaryLocation") else []
        locations += [loc["Name"] for loc in req.get("secondaryLocations", []) if loc.get("Name")]

        jobs.append({
            "source": source,
            "external_id": req["Id"],
            "title": req.get("Title"),
            "company": source,
            "location": "; ".join(locations) or None,
            "url": f"https://{host}/hcmUI/CandidateExperience/en/sites/{site_number}/job/{req['Id']}",
            "description": None,
        })

    return jobs


def _fetch_raw(host: str, site_number: str, keyword: str = "", limit: int = 25, offset: int = 0) -> dict:
    """
    Shared by fetch_live_search and add_company.py's verifier -- does the
    actual GET and returns the raw recruitingCEJobRequisitions JSON, so the
    verifier can also read parse_total_jobs_count() out of it without
    duplicating the request logic.

    Oracle Recruiting Cloud (Fusion HCM) candidate-experience pages are
    client-side (React/ADF) and so don't show ready-made job HTML, but the
    underlying recruitingCEJobRequisitions resource is -- just like Workday's
    CxS API -- a public JSON endpoint with no login needed, the same fixed
    path under /hcmRestApi/resources/latest/ for every visitor/tenant.

    `host` is the fa(.ocs).oraclecloud.com hostname from the candidate-experience
    link in the careers page source (e.g. "jpmc.fa.oraclecloud.com" for JPMorgan,
    "iaziqy.fa.ocs.oraclecloud.com" for Uber). `site_number` is the SiteNumber
    from that same link (the "sites/{site_number}" segment, e.g. "CX_1001" and
    "UberCareers" respectively). `keyword` filters server-side just like
    Workday's searchText.
    """
    finder = (
        f"findReqs;siteNumber={site_number},facetsList=LOCATIONS;WORK_LOCATIONS;"
        f"WORKPLACE_TYPES;TITLES;CATEGORIES;ORGANIZATIONS;POSTING_DATES;FLEX_FIELDS,"
        f"limit={limit},offset={offset},sortBy=POSTING_DATES_DESC"
    )
    if keyword:
        finder += f",keyword={keyword}"

    response = requests.get(
        f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        params={
            "onlyData": "true",
            "expand": "requisitionList.secondaryLocations,flexFieldsFacet.values",
            "finder": finder,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def parse_total_jobs_count(data: dict) -> int | None:
    """
    `data`'s own top-level "count" field is just the wrapper's item count
    (always 1 -- one "search" object per call, see parse_search_results), NOT
    a job count -- don't confuse the two. The real total is
    items[0]["TotalJobsCount"] (found live: JPMorgan Chase's unfiltered
    call here returns 25 requisitions on this page but TotalJobsCount=7322).
    """
    items = data.get("items") or []
    if not items:
        return None
    return items[0].get("TotalJobsCount")


def fetch_live_search(
    host: str, site_number: str, source: str, keyword: str = "", limit: int = 25, offset: int = 0
) -> list[dict]:
    """
    See _fetch_raw for the underlying API. This wraps it and returns just the
    parsed job list -- NOTE: only one page (`limit`, default 25) is fetched,
    no loop over the tenant's real total (see parse_total_jobs_count); a
    broad/no-keyword search against a large tenant can silently miss
    postings past this page in scheduler.py's production scrape.
    """
    data = _fetch_raw(host, site_number, keyword=keyword, limit=limit, offset=offset)
    return parse_search_results(data, host, site_number, source)
