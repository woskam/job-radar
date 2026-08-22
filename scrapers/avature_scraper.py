import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def parse_search_results(data: list[dict], base_url: str, source: str) -> list[dict]:
    jobs = []

    for entry in data:
        # "location" comes back as e.g. "Utrecht - " (always with a trailing " - ",
        # even when no city is known -- in that case it's just "").
        location = (entry.get("location") or "").rstrip(" -") or None

        jobs.append({
            "source": source,
            "external_id": str(entry["id"]),
            "title": entry.get("label") or entry.get("value"),
            "company": source,
            "location": location,
            # The real URL slug (from the job title) doesn't need to be correct --
            # Avature's old portal template renders the JobDetail page fine even
            # with an arbitrary placeholder slug, as long as the trailing numeric
            # ID is correct.
            "url": f"{base_url.rstrip('/')}/en_US/jobs/JobDetail/job/{entry['id']}",
            "description": None,
        })

    return jobs


def fetch_live_search(base_url: str, source: str, keywords: str = "") -> list[dict]:
    """
    These older Avature portal templates (e.g. L'Oréal, portal/196) don't run
    an Angular/React SPA with a separate /api/vacancy endpoint like the
    modern Avature career sites -- it's a jQuery widget (SearchJobs.js) that
    fetches a public JSON list at /en_US/jobs/SearchJobsAJAXJSON/<keywords>,
    no login needed. The UI uses the same endpoint for the "live search"
    suggestions under the search bar, so it searches broadly (both title and
    location already match on this one term) and always returns at most ~20
    results -- no pagination/offset parameter was found for this route.

    NOTE: this template type is NOT universal across all Avature tenants.
    Goldman Sachs' higher.gs.com/results, for instance, is a completely
    different, custom-built Next.js/Apollo GraphQL app (endpoint
    https://api-higher.gs.com/gateway/api/v1/graphql, operation "GetRoles")
    whose roleSearch query expects a Bearer token that turned out impossible
    to obtain without a logged-in browser session (Okta) -- Avature is
    apparently only used there for candidate events
    (recruiting360.avature.net), not for the general job search. Same as
    with IKEA's Radancy instance, so left aside until another approach is
    found.
    """
    resp = requests.get(
        f"{base_url.rstrip('/')}/en_US/jobs/SearchJobsAJAXJSON/{keywords}",
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    return parse_search_results(resp.json(), base_url, source)
