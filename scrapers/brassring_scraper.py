import re

import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
RFT_RE = re.compile(r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"')
COOKIEVALUE_RE = re.compile(r'id="CookieValue"\s+type="hidden"\s+value="([^"]*)"')


def parse_search_results(data: dict, partner_id: str, site_id: str, source: str) -> list[dict]:
    jobs = []

    for job in (data.get("Jobs") or {}).get("Job") or []:
        # BrassRing doesn't return fixed fields per job, but a list
        # "Questions" with QuestionName/Value pairs (which fields are in
        # there is configurable per tenant) -- hence converting to a dict first.
        answers = {q["QuestionName"]: q.get("Value") for q in job.get("Questions", [])}
        reqid = answers.get("reqid")
        title = answers.get("jobtitle")
        if not reqid or not title:
            continue

        jobs.append({
            "source": source,
            "external_id": reqid,
            "title": title,
            "company": source,
            # Guess' BrassRing tenant doesn't return a location per job in the
            # Questions set (only jobtitle/jobdescription/reqid/autoreq/...).
            # Location IS present in the response, but only as a facet
            # aggregate ("Los Angeles, CA": 6 jobs) with no reliable 1:1
            # mapping to an individual job -- so deliberately always None here.
            "location": None,
            "url": job.get("Link") or (
                "https://sjobs.brassring.com/TGnewUI/Search/home/HomeWithPreLoad"
                f"?partnerid={partner_id}&siteid={site_id}&PageType=JobDetails&jobid={reqid}"
            ),
            "description": None,
        })

    return jobs


def fetch_live_search(
    partner_id: str, site_id: str, source: str, keywords: str = "", location: str = ""
) -> list[dict]:
    """
    BrassRing (Kenexa/IBM) Talent Gateway is an old Angular 1.8 SPA (TGNewUI):
    the search results are NOT already in the first HTML response, but only
    load after a POST to a CSRF-protected AJAX endpoint. Still no JS
    rendering needed to scrape this -- plain requests suffice:

      1. GET the search page (with PageType=searchResults) to grab cookies +
         the anti-CSRF token (__RequestVerificationToken, needed as the
         "RFT" header) + the EncryptedSessionValue (hidden field #CookieValue).
      2. POST those two values to /TgNewUI/Search/Ajax/PowerSearchJobs.

    Tested with Guess Corporate Careers (partner_id="25813", site_id="5178"):
    returned 13 jobs without a keyword, 5 with keyword="sales" (server-side
    filter, so it works). No login/account needed, just a session/cookie.
    """
    session = requests.Session()
    headers = {"User-Agent": USER_AGENT}

    home_url = (
        "https://sjobs.brassring.com/TGnewUI/Search/home/HomeWithPreLoad"
        f"?partnerid={partner_id}&siteid={site_id}&PageType=searchResults&SearchType=linkquery"
    )
    home_resp = session.get(home_url, headers=headers, timeout=15)
    home_resp.raise_for_status()

    rft_match = RFT_RE.search(home_resp.text)
    if not rft_match:
        raise RuntimeError(f"No __RequestVerificationToken found at {home_url} -- unknown BrassRing template")
    cookieval_match = COOKIEVALUE_RE.search(home_resp.text)

    payload = {
        "PartnerId": partner_id,
        "SiteId": site_id,
        "Keyword": keywords,
        "Location": location,
        "TurnOffHttps": False,
        "Latitude": 0,
        "Longitude": 0,
        "FacetFilterFields": {"Facet": []},
        "PowerSearchOptions": {"PowerSearchOption": []},
        "SortType": "",
        "EncryptedSessionValue": cookieval_match.group(1) if cookieval_match else "",
    }

    search_resp = session.post(
        "https://sjobs.brassring.com/TgNewUI/Search/Ajax/PowerSearchJobs",
        json=payload,
        headers={**headers, "RFT": rft_match.group(1), "Referer": home_url},
        timeout=15,
    )
    search_resp.raise_for_status()
    return parse_search_results(search_resp.json(), partner_id, site_id, source)
