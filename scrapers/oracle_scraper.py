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


def fetch_live_search(
    host: str, site_number: str, source: str, keyword: str = "", limit: int = 25, offset: int = 0
) -> list[dict]:
    """
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
    return parse_search_results(response.json(), host, site_number, source)
