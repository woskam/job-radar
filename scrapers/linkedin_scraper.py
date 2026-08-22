from bs4 import BeautifulSoup


def parse_search_results(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs = []

    for card in soup.select(".job-search-card"):
        link = card.select_one(".job-search-card__link")
        company = card.select_one(".job-search-card__company")
        location = card.select_one(".job-search-card__location")

        if not link:
            continue

        jobs.append({
            "source": "linkedin",
            "external_id": link["href"].rstrip("/").rsplit("/", 1)[-1],
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

    The real LinkedIn login flow (credentials, 2FA handling, session cookies,
    rate limiting) is deliberately not implemented here. LinkedIn's structure
    and anti-scraping measures change regularly, and using
    LINKEDIN_EMAIL/LINKEDIN_PASSWORD from .env must first be tested together
    against a test session before this ever goes into the scheduler (see the
    CLAUDE.md restriction: no live scraping against the real account without
    approval).
    """
    raise NotImplementedError(
        "Live LinkedIn scraping isn't built/approved yet. "
        "Test and approve the login flow separately before this is used."
    )
