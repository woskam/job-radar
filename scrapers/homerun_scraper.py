import xml.etree.ElementTree as ET

import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}


def parse_search_results(xml_text: str, source: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    jobs = []

    for entry in root.findall("a:entry", ATOM_NS):
        link_el = entry.find("a:link[@rel='alternate']", ATOM_NS)
        location_el = entry.find("a:location/a:name", ATOM_NS)

        jobs.append({
            "source": source,
            "external_id": entry.findtext("a:id", default=None, namespaces=ATOM_NS),
            "title": entry.findtext("a:title", default=None, namespaces=ATOM_NS),
            "company": source,
            "location": location_el.text if location_el is not None else None,
            "url": link_el.get("href") if link_el is not None else None,
            "description": None,
        })

    return jobs


def fetch_live_search(feed_slug: str, source: str) -> list[dict]:
    """
    Homerun (confirmed via the "static.homerun.co/employers/v3/..." scripts)
    offers, besides the widget, a public Atom feed with all current jobs, no
    login needed: https://feed.homerun.co/{feed_slug} -- for Douglas found
    via the <link rel="alternate" type="application/atom+xml"> tag in the
    HTML source of vacatures.douglas.nl (feed_slug there is "douglas"). The
    feed even contains the full job description (<description>), but we
    deliberately leave that as None to keep the schema consistent with the
    other scrapers.
    """
    resp = requests.get(
        f"https://feed.homerun.co/{feed_slug}",
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    return parse_search_results(resp.text, source)
