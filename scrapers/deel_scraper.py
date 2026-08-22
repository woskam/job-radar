import json

import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
PUSH_MARKER = "self.__next_f.push("


def _dig(obj, key: str):
    # Recursively searches for the first key "jobPostings" somewhere in the
    # nested React Server Components flight payload (list/dict structure
    # mixing $-tags and props) -- the exact nesting depth differs per
    # Next.js build, so a fixed path lookup is too fragile.
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            found = _dig(value, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _dig(value, key)
            if found is not None:
                return found
    return None


def _extract_job_postings(html: str) -> list[dict]:
    """
    jobs.deel.com is a Next.js App Router site: the full job list is already
    server-side rendered into the HTML, spread across multiple
    `<script>self.__next_f.push([1,"<chunk>"])</script>` tags (React Flight
    protocol). Each "push" argument is itself a valid JSON value
    ([1, "N:<json-or-something-else>"]), so we parse those with the standard
    json decoder (raw_decode, instead of a regex that would choke on nested
    brackets/quotes) and look for the chunk containing "jobPostings".
    """
    decoder = json.JSONDecoder()
    pos = 0

    while True:
        idx = html.find(PUSH_MARKER, pos)
        if idx == -1:
            return []

        json_start = idx + len(PUSH_MARKER)
        try:
            push_arg, end = decoder.raw_decode(html, json_start)
        except json.JSONDecodeError:
            pos = json_start
            continue

        pos = end  # raw_decode returns an ABSOLUTE index, not a length

        if not (isinstance(push_arg, list) and len(push_arg) == 2 and isinstance(push_arg[1], str)):
            continue

        chunk = push_arg[1]
        if "jobPostings" not in chunk:
            continue

        # Each chunk starts with "<segment-id>:" followed by the actual payload
        _, _, rest = chunk.partition(":")
        try:
            payload = json.loads(rest)
        except json.JSONDecodeError:
            continue

        postings = _dig(payload, "jobPostings")
        if postings:
            return postings


def parse_search_results(html: str, company_slug: str, source: str) -> list[dict]:
    jobs = []

    for posting in _extract_job_postings(html):
        external_id = posting.get("id")
        title = posting.get("title")
        if not external_id or not title:
            continue

        job_info = posting.get("job") or {}
        location_names = [
            loc["location"]["name"]
            for loc in job_info.get("jobLocations", [])
            if loc.get("location", {}).get("name")
        ]

        jobs.append({
            "source": source,
            "external_id": external_id,
            "title": title.strip(),
            "company": source,
            "location": ", ".join(location_names) or None,
            "url": f"https://jobs.deel.com/{company_slug}/job-details/{external_id}/overview",
            "description": None,
        })

    return jobs


def fetch_live_search(company_slug: str, source: str, keywords: str = "", location: str = "") -> list[dict]:
    """
    No separate public JSON endpoint found for jobs.deel.com -- the
    Content-Security-Policy only allows client-side fetches to
    api-prod.letsdeel.com, but that requires a bearer token (see
    developer.deel.com/api/ats-guides). The full job list is, however,
    already unprotected in the server-side rendered HTML (React Flight
    payload, see _extract_job_postings), so we just fetch the public board
    page.

    Tested with company_slug="klarna": https://jobs.deel.com/klarna returns
    all 91 jobs in a single GET, regardless of query string -- a
    ?location=...  param doesn't change the server response at all (the
    filter works purely client-side in the browser on the already-loaded
    list). So we filter here ourselves, client-side, on keywords (title) and
    location (substring, case-insensitive).
    """
    resp = requests.get(
        f"https://jobs.deel.com/{company_slug}",
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    resp.raise_for_status()
    jobs = parse_search_results(resp.text, company_slug, source)

    if keywords:
        kw = keywords.lower()
        jobs = [j for j in jobs if kw in (j["title"] or "").lower()]

    if location:
        loc = location.lower()
        jobs = [j for j in jobs if j["location"] and loc in j["location"].lower()]

    return jobs
