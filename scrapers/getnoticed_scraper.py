from urllib.parse import urlparse

import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
MAX_PAGE_SIZE = 10  # GetNoticed's /api/vacancy/ ignores a higher limit/maxPerPage param, caps itself at 10


def _origin(base_url: str) -> str:
    # career_url in companies.yaml points at the overview page (e.g.
    # "https://jobs.kpn.com/vacatures"), but the API endpoint lives under the
    # root of the site. So trim back to scheme+host, whatever comes in
    # ("https://host", "https://host/", "https://host/vacatures").
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def parse_search_results(data: dict, base_url: str, source: str) -> list[dict]:
    origin = _origin(base_url)
    jobs = []

    for vacancy in data.get("vacancies", []):
        external_id = str(vacancy["id"])

        jobs.append({
            "source": source,
            "external_id": external_id,
            "title": vacancy.get("title"),
            "company": source,
            # GetNoticed tenants aren't consistent here: some (Odido) set a
            # real per-job "city" on the vacancy itself, others (KPN) omit
            # that field and only have a "company" sub-object with the fixed
            # HQ location (for KPN, "Rotterdam" for every job, so not usable
            # as the job's location) -- hence no fallback to company.city here.
            "location": vacancy.get("city"),
            "url": f"{origin}/vacature/{vacancy['id']}/{vacancy.get('slug', '')}".rstrip("/"),
            "description": None,
        })

    return jobs


def fetch_live_search(base_url: str, source: str, keywords: str = "", limit: int = 200) -> list[dict]:
    """
    GetNoticed (NL career-site platform/CMS, used by e.g. KPN and Odido/T-Mobile NL)
    does NOT render jobs server-side on /vacatures -- that's an empty template
    filled in client-side. No login needed, but a few steps to get to the
    right source:

    - First guess was `/fuse/vacancies.json` (present as `data-vacancies-src`
      in the HTML on sites with a Fuse.js client search, like KPN) -- a
      static dump of ALL jobs (id/title/url/description_plain), without
      location and without server-side keyword filtering (query params are
      ignored). Doesn't exist on every tenant (Odido 404s on it, uses the
      "regular" AJAX search instead of the Fuse variant).
    - The actually usable source is `{origin}/api/vacancy/`, the JSON
      endpoint that fills the "#vacancy-results" grid on the overview page
      (found via Routing.generate("vacancy_get") in the bundled JS -> route
      "vacancy_get" = "/api/vacancy/"). Works on BOTH KPN and Odido (same
      platform version), so presumably generic across GetNoticed tenants.
      Requires the header `X-Requested-With: XMLHttpRequest` -- without that
      header you get the full HTML page back (KPN: HTTP 200 with HTML;
      Odido: HTTP 404) instead of JSON.
    - `search=<keyword>` DOES filter server-side here (tested: KPN
      ?search=devops -> 8/39 hits, Odido ?search=engineer -> 0/48 hits,
      ?search=shop -> 34/48 hits) -- so contrary to the first impression
      (based on /fuse/vacancies.json), no custom client-side filtering needs
      to be built.
    - Pagination via `pageNumber` (1-based); response contains
      meta.totalPageCount and meta.num_total_hits. maxPerPage is fixed at 10,
      a higher `limit` param is ignored.
    - Location: only reliably present as a top-level "city" field on the job
      itself (Odido) -- see parse_search_results for why company.city isn't
      used.
    """
    session = requests.Session()
    jobs: dict[str, dict] = {}
    page = 1

    while len(jobs) < limit:
        resp = session.get(
            f"{_origin(base_url)}/api/vacancy/",
            params={"search": keywords, "pageNumber": page},
            headers={"User-Agent": USER_AGENT, "X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        page_jobs = parse_search_results(data, base_url, source)
        if not page_jobs:
            break

        for job in page_jobs:
            jobs[job["external_id"]] = job

        total_pages = data.get("meta", {}).get("totalPageCount", page)
        if page >= total_pages:
            break
        page += 1

    return list(jobs.values())[:limit]
