import xml.etree.ElementTree as ET

import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def parse_search_results(xml_bytes: bytes, handle: str, source: str) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    jobs = []

    for position in root.findall("position"):
        external_id = position.findtext("id")
        if not external_id:
            continue

        offices = [position.findtext("office")] + [
            o.text for o in position.findall("additionalOffices/office")
        ]
        location = ", ".join(o for o in offices if o) or None

        jobs.append({
            "source": source,
            "external_id": external_id,
            "title": position.findtext("name"),
            "company": source,
            "location": location,
            "url": f"https://{handle}.jobs.personio.de/job/{external_id}",
            # jobDescriptions is present in the schema but empty on every
            # tenant checked so far -- None here, same as Greenhouse, rather
            # than an extra per-posting request just to confirm it's blank.
            "description": None,
        })

    return jobs


def fetch_live_search(handle: str, source: str) -> list[dict]:
    """
    Personio's XML job feed is public and documented (no login needed):
    support.personio.de/hc/en-us/articles/207576365-Integrate-jobs-from-Personio-into-your-website-via-XML
    -- returns a company's full current job list in a single GET call, no
    keyword param, same shape as Ashby/Greenhouse (filtering on keywords
    happens downstream in matching/scorer.py).

    `handle` is the subdomain in the company's own
    https://{handle}.jobs.personio.de careers site (some tenants use
    .com instead of .de for the human-facing site, but the XML feed itself
    is reliably under .de per Personio's own docs -- confirmed live against
    several real tenants).
    """
    resp = requests.get(
        f"https://{handle}.jobs.personio.de/xml",
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    # resp.content (raw bytes), not resp.text -- Personio's response has no
    # charset in its Content-Type header, so requests' text-decoding falls
    # back to guessing and mangles non-ASCII characters (confirmed live: an
    # en-dash in a real job title came through as "â"). ET.fromstring on
    # the raw bytes respects the XML declaration's own encoding="UTF-8"
    # instead.
    return parse_search_results(resp.content, handle, source)
