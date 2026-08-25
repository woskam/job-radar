import requests


def parse_search_results(data: dict, host: str, site: str, source: str) -> list[dict]:
    jobs = []

    for posting in data.get("jobPostings", []):
        # Some postings apparently lack 'externalPath' (crashed the entire
        # 3-hourly scrape run at 21:00 -- KeyError). Without a path we can't
        # build a usable URL, so skip that posting instead of crashing the rest.
        external_path = posting.get("externalPath")
        if not external_path:
            continue

        bullet_fields = posting.get("bulletFields") or []
        external_id = bullet_fields[0] if bullet_fields else external_path

        # Not every tenant populates locationsText (Accenture: always null) --
        # those tenants instead put it as the second bulletFields entry
        # (the first being the requisition id), e.g. ["R00325340", "Gurugram"]
        # or ["ATCI-5479554-S1999860", "Bengaluru"]. Only used as a fallback,
        # so tenants where locationsText already works are unaffected.
        location = posting.get("locationsText") or (bullet_fields[1] if len(bullet_fields) > 1 else None)

        jobs.append({
            "source": source,
            "external_id": external_id,
            "title": posting.get("title"),
            "company": source,
            "location": location,
            # No /en-US/ segment -- that's purely the Workday site language, not
            # the job's own country (Philips' "jobs-and-careers" tenant is e.g.
            # worldwide, with Eindhoven among them); without that misleading
            # suggestion the link is more neutral.
            "url": f"https://{host}/{site}{external_path}",
            "description": None,
        })

    return jobs


def fetch_live_search(host: str, site: str, search_text: str = "", limit: int = 20, offset: int = 0) -> dict:
    """
    Workday's Candidate Experience Service (CxS) is a public JSON API,
    no login needed -- unlike LinkedIn/Indeed, so directly usable.
    `host` is e.g. "newbalance.wd1.myworkdayjobs.com", `site` is e.g. "Careers".
    """
    tenant = host.split(".")[0]
    response = requests.post(
        f"https://{host}/wday/cxs/{tenant}/{site}/jobs",
        json={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": search_text},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()
