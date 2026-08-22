from bs4 import BeautifulSoup


def parse_search_results(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs = []

    for card in soup.select(".job_seen_beacon"):
        link = card.select_one(".jcs-JobTitle")
        company = card.select_one(".companyName")
        location = card.select_one(".companyLocation")

        if not link:
            continue

        jobs.append({
            "source": "indeed",
            "external_id": link["href"].split("jk=", 1)[-1],
            "title": link.get_text(strip=True),
            "company": company.get_text(strip=True) if company else None,
            "location": location.get_text(strip=True) if location else None,
            "url": link["href"],
            "description": None,
        })

    return jobs


def fetch_live_search(keywords: str, location: str) -> str:
    """
    DO NOT CALL without explicit approval.

    The real Indeed login flow (credentials, session cookies, rate limiting,
    possible captchas) is deliberately not implemented here. Test and
    approve this separately before the account is used for it (see the
    CLAUDE.md restriction: no live scraping against the real account without
    approval).
    """
    raise NotImplementedError(
        "Live Indeed scraping isn't built/approved yet. "
        "Test and approve the login flow separately before this is used."
    )
