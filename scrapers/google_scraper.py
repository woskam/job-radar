import html
import json
import re

import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
SEARCH_URL = "https://www.google.com/about/careers/applications/jobs/results/"

# Google's careers site has no public ATS-style API -- it's a custom Closure
# ("WIZ") app that server-renders its own internal page state as a series of
# `AF_initDataCallback({key: 'ds:N', hash: '...', data: [...]});` blocks. One
# of those blocks (which ds:N it is isn't stable -- observed as ds:1, but
# nothing guarantees that) holds the job list, each entry roughly:
#   [external_id, title, apply_url, [.., description_html], .., locations, ..]
# where `locations` (index 9) is a list of ["City, Country", [address], ...]
# tuples. This is reverse-engineered from the live page (2026-08-24), not a
# documented API -- more fragile than the other scrapers here, since Google
# could restructure this at any time without notice.
CALLBACK_RE = re.compile(r"AF_initDataCallback\(\{key: '(ds:\d+)', hash: '\d+', data:")
LOCATIONS_FIELD = 9


def _extract_data_blocks(html_text: str) -> dict:
    decoder = json.JSONDecoder()
    blocks = {}
    for match in CALLBACK_RE.finditer(html_text):
        try:
            data, _ = decoder.raw_decode(html_text, match.end())
        except json.JSONDecodeError:
            continue
        blocks[match.group(1)] = data
    return blocks


def _find_job_entries(blocks: dict) -> list:
    # Identify the job-list block by shape, not by which ds:N key it landed
    # on: a list of lists, where each inner entry starts with a numeric-string
    # id and has a "signin?jobId=" apply URL as its third element.
    for data in blocks.values():
        if not (isinstance(data, list) and data and isinstance(data[0], list) and data[0]):
            continue
        first = data[0][0]
        if (
            isinstance(first, list) and len(first) > LOCATIONS_FIELD
            and isinstance(first[0], str) and first[0].isdigit()
            and isinstance(first[2], str) and "signin?jobId=" in first[2]
        ):
            return data[0]
    return []


def parse_search_results(html_text: str, source: str) -> list[dict]:
    jobs: dict[str, dict] = {}

    for entry in _find_job_entries(_extract_data_blocks(html_text)):
        if len(entry) <= LOCATIONS_FIELD:
            continue
        external_id = entry[0]
        if external_id in jobs:
            continue

        locations = entry[LOCATIONS_FIELD] or []
        location = "; ".join(loc[0] for loc in locations if loc) or None

        jobs[external_id] = {
            "source": source,
            "external_id": external_id,
            "title": html.unescape(entry[1]) if entry[1] else entry[1],
            "company": source,
            "location": location,
            "url": entry[2],
            "description": None,
        }

    return list(jobs.values())


def fetch_live_search(source: str, keywords: str = "", location: str = "Netherlands") -> list[dict]:
    """
    `?location=<..>&q=<..>` genuinely filters server-side (confirmed live:
    location=Netherlands vs location=Germany return completely different job
    sets, and adding q=manager narrows further) -- not cosmetic like some of
    the other platforms here. Defaults to Netherlands since without it this
    returns Google's entire global job list.
    """
    resp = requests.get(
        SEARCH_URL,
        params={"location": location, "q": keywords},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    return parse_search_results(resp.text, source)
