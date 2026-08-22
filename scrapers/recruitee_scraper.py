import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def parse_search_results(data: dict, company_slug: str, source: str) -> list[dict]:
    jobs = []

    for offer in data.get("offers", []):
        external_id = offer.get("id")
        if external_id is None:
            continue

        jobs.append({
            "source": source,
            "external_id": str(external_id),
            "title": offer.get("title"),
            "company": source,
            "location": offer.get("location") or None,
            "url": offer.get("careers_url") or f"https://{company_slug}.recruitee.com/o/{offer.get('slug')}",
            "description": None,
        })

    return jobs


def fetch_live_search(company_slug: str, source: str, keywords: str = "") -> list[dict]:
    """
    Recruitee has a documented public JSON API with no auth:
    GET https://{company_slug}.recruitee.com/api/offers/ -- no login needed.
    Tested with bunq (company_slug="bunq"): returns all published jobs in one
    go (12 of them at test time), no pagination. The API itself doesn't
    support a search parameter, so `keywords` filters client-side on title
    (substring, case-insensitive).
    """
    resp = requests.get(
        f"https://{company_slug}.recruitee.com/api/offers/",
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    jobs = parse_search_results(resp.json(), company_slug, source)

    if keywords:
        kw = keywords.lower()
        jobs = [j for j in jobs if kw in (j["title"] or "").lower()]

    return jobs
