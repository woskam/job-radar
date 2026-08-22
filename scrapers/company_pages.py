from bs4 import BeautifulSoup


def parse_company_page(html: str, source: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs = []

    for listing in soup.select(".job-listing"):
        link = listing.select_one(".job-link")
        location = listing.select_one(".job-location")
        description = listing.select_one(".job-description")

        if not link:
            continue

        jobs.append({
            "source": source,
            "external_id": link["href"].rsplit("/", 1)[-1],
            "title": link.get_text(strip=True),
            "company": source,
            "location": location.get_text(strip=True) if location else None,
            "url": link["href"],
            "description": description.get_text(strip=True) if description else None,
        })

    return jobs
