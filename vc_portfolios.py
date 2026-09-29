"""
One candidate-lister function per VC, feeding bulk_add_from_vc.py's shared
pipeline (bulk_add_common.py) -- the VC-portfolio equivalent of
scrapers/*.py, where each module knows one platform's shape. Every lister
returns candidates in the common shape: {"name", "website", "category",
"source_note"}.

Unlike YCombinator (a single public JSON directory, see
bulk_add_from_yc.py), no other VC has an equivalent structured API -- each
one's portfolio page is its own bespoke reverse-engineering project.
Researched 2026-09-22, checked against the raw HTML fetched the same way
add_company.py's fetch() does:

  IMPLEMENTED:
    - balderton: WordPress + FacetWP, each company card already has the
      real external website (no extra hop). FacetWP's own AJAX pagination
      endpoint (wp-json/facetwp/v1/refresh) was attempted for the full
      ~205-company list but returned empty results despite matching the
      page's own FWP_JSON config -- not worth more time chasing a fragile
      undocumented payload shape, so this only covers the ~30 companies
      statically present on https://www.balderton.com/companies/ (the
      "live" -- i.e. not exited/acquired -- ones, filtered from the class
      list). Revisit if the AJAX contract is worth solving later.

    - northzone (northzone.com/portfolio): Webflow CMS + FinSweet CMS
      Filter. The listing has 264 card links to /portfolio/<slug> (132
      unique companies, each rendered twice) with a hidden
      fs-cmsfilter-field="status" per card -- 106 Active, 16 IPO, 13
      Acquired at research time (2026-09-29); only Active is taken. Each
      detail page's <h1> gives the name and an <a> whose visible text is
      exactly "company website" gives the real external URL -- one extra
      fetch per company, same shape as balderton but with a hop.

    - accel (accel.com/companies): 152 unique /companies/<slug> links, no
      pagination needed -- all present in the raw HTML already. Each
      detail page's <h1> is a marketing tagline, not the name, so the
      name comes from <title> instead (format "Accel | <Name>"); the real
      external site is the <a aria-label="Website"> link (the page also
      has Twitter/YouTube/LinkedIn links, each with their own aria-label,
      so this reliably picks the right one).

    - index_ventures (indexventures.com/companies): 341 links to
      /companies/<slug>/ (339 unique once the bare /companies/ nav links
      are excluded). Each detail page's <h1> gives the name; the real
      external site is the <a> whose visible text ends in "Opens in a new
      window." (confirmed against wiz.io/figma.com/revolut.com), after
      excluding indexventures.com/x.com/linkedin.com/notoptional.eu --
      the last one is the web agency that built index's own site and
      appears on every single detail page.

  SKIPPED (JS-rendered / image-carousel, no data in raw HTML -- confirmed
  with Wychert, not worth a headless browser per CLAUDE.md's "last resort,
  not a recurring dependency"):
    - a16z (a16z.com/portfolio): image carousel, no links/JSON in raw HTML.
    - Atomico (atomico.com/portfolio): HTTP 429 on first request --
      treated as rate-limiting, not pushed further.
    - Lakestar (lakestar.com/portfolio): logo images only, no links.

  SKIPPED (confirmed but low-yield or not fully solvable without a
  headless browser -- not worth building a bespoke parser for):
    - Sequoia Capital (sequoiacap.com/our-companies): only ~21 curated
      companies in raw HTML, not the full portfolio -- too small a yield
      to justify a dedicated parser.
    - EQT Ventures (eqtgroup.com/private-capital/eqt-ventures): the
      "Browse all companies" URL
      (/about/current-portfolio?fund=eqt_ventures_i,eqt_ventures_ii,eqt_ventures_iii)
      exists, but its raw HTML only contains 30 unique companies -- the
      rest sits behind client-side pagination/infinite-scroll that a
      plain GET doesn't reach.
"""
import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from add_company import fetch

# Politeness delay between the extra per-company detail-page fetches inside
# the listers below (northzone/accel/index_ventures each need one on top of
# the listing page itself) -- lighter than bulk_add_common.run_bulk's own
# 1.5s default since every request here lands on the *same* VC site, not a
# spread of different companies' sites, but still not hammering it bare.
DETAIL_FETCH_DELAY = 0.5

BALDERTON_URL = "https://www.balderton.com/companies/"
NORTHZONE_URL = "https://northzone.com/portfolio"
ACCEL_URL = "https://accel.com/companies"
INDEX_VENTURES_URL = "https://www.indexventures.com/companies/"

INDEX_VENTURES_EXCLUDED_DOMAINS = ("indexventures.com", "x.com", "twitter.com", "linkedin.com", "notoptional.eu")


def _hostname_matches(href: str, domains: tuple[str, ...]) -> bool:
    """True if href's hostname is one of `domains` or a subdomain of one --
    a plain substring check (e.g. "x.com" in href) would wrongly exclude
    any company whose own domain happens to end in "x.com", like
    roblox.com (confirmed live: this bit index_ventures_candidates)."""
    host = (urlparse(href).hostname or "").lower()
    return any(host == d or host.endswith(f".{d}") for d in domains)


def balderton_candidates() -> list[dict]:
    resp = fetch(BALDERTON_URL)
    if resp is None:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    candidates = []
    seen_names = set()
    for card in soup.select("div.type-company"):
        classes = card.get("class", [])
        if "status-live" not in classes:
            # Skip exited/acquired companies -- not hiring, not useful here.
            continue

        h3 = card.find("h3")
        link = card.find("a", class_="mask")
        if not h3 or not link or not link.get("href"):
            continue
        name = h3.get_text(strip=True)
        if name.lower() in seen_names:
            # The same card sometimes appears more than once in the raw
            # HTML (seen with "Cleo") -- likely rendered twice for two
            # different filter states. One entry is enough.
            continue
        seen_names.add(name.lower())

        sector = next((c[len("sector-"):] for c in classes if c.startswith("sector-")), None)
        category = sector.replace("-", "_") if sector else "startup"

        candidates.append({
            "name": name,
            "website": link["href"].strip(),
            "category": category,
            "source_note": "sourced via Balderton Capital's public portfolio page",
        })
    return candidates


def _northzone_active_rows() -> list[tuple[str, str]]:
    """Returns [(slug, name), ...] for Active companies, across both pages
    of Northzone's Webflow CMS pagination (100 companies per page -- a
    ?<hash>_page=2 link only appears, itself hidden, when a second page
    exists; there were exactly 2 pages at research time, 142 companies
    total). This table view (div.filters5_company-item) is the one that
    reliably carries both fs-cmsfilter-field="status" and "name" per row
    -- an earlier attempt using the card grid (div.filter5_item) found
    each company rendered multiple times with the status marker present
    on only one occurrence, which silently dropped most Active companies
    when deduped by first-seen slug."""
    rows: list[tuple[str, str]] = []
    url = NORTHZONE_URL
    while url:
        resp = fetch(url)
        if resp is None:
            break
        soup = BeautifulSoup(resp.text, "html.parser")
        for row in soup.select("div.filters5_company-item"):
            link = row.find("a", href=True)
            name_el = row.select_one('[fs-cmsfilter-field="name"]')
            status_el = row.select_one('[fs-cmsfilter-field="status"]')
            if not link or not name_el or not status_el:
                continue
            if status_el.get_text(strip=True) != "Active":
                continue
            slug = link["href"].removeprefix("/portfolio/").strip("/")
            if slug:
                rows.append((slug, name_el.get_text(strip=True)))

        next_link = soup.select_one(".w-pagination-next")
        url = f"{NORTHZONE_URL}{next_link['href']}" if next_link and next_link.get("href") else None
        if url:
            time.sleep(DETAIL_FETCH_DELAY)
    return rows


def northzone_candidates() -> list[dict]:
    rows = _northzone_active_rows()

    candidates = []
    for slug, name in rows:
        time.sleep(DETAIL_FETCH_DELAY)
        detail_resp = fetch(f"https://northzone.com/portfolio/{slug}")
        if detail_resp is None:
            continue
        detail = BeautifulSoup(detail_resp.text, "html.parser")
        website_link = next(
            (a for a in detail.find_all("a", href=True) if a.get_text(strip=True).lower() == "company website"),
            None,
        )
        if not website_link:
            continue
        candidates.append({
            "name": name,
            "website": website_link["href"].strip(),
            "category": "startup",
            "source_note": "sourced via Northzone's public portfolio page",
        })
    return candidates


def accel_candidates() -> list[dict]:
    resp = fetch(ACCEL_URL)
    if resp is None:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    slugs = []
    seen_slugs = set()
    for link in soup.select('a[href^="/companies/"]'):
        slug = link.get("href", "").removeprefix("/companies/").strip("/")
        if slug and slug not in seen_slugs:
            seen_slugs.add(slug)
            slugs.append(slug)

    candidates = []
    for slug in slugs:
        time.sleep(DETAIL_FETCH_DELAY)
        detail_resp = fetch(f"https://accel.com/companies/{slug}")
        if detail_resp is None:
            continue
        detail = BeautifulSoup(detail_resp.text, "html.parser")
        # The <h1> on these pages is the marketing tagline, not the
        # company name -- <title> ("Accel | <Name>") has the real name.
        title = detail.title.get_text(strip=True) if detail.title else ""
        name = title.split("|", 1)[-1].strip() if "|" in title else None
        website_link = detail.find("a", attrs={"aria-label": "Website"})
        if not name or not website_link or not website_link.get("href"):
            continue
        candidates.append({
            "name": name,
            "website": website_link["href"].strip(),
            "category": "startup",
            "source_note": "sourced via Accel's public portfolio page",
        })
    return candidates


def index_ventures_candidates() -> list[dict]:
    resp = fetch(INDEX_VENTURES_URL)
    if resp is None:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    slugs = []
    seen_slugs = set()
    for link in soup.select('a[href^="/companies/"]'):
        slug = link.get("href", "").removeprefix("/companies/").strip("/")
        if slug and slug not in seen_slugs:
            seen_slugs.add(slug)
            slugs.append(slug)

    candidates = []
    for slug in slugs:
        time.sleep(DETAIL_FETCH_DELAY)
        detail_resp = fetch(f"https://www.indexventures.com/companies/{slug}/")
        if detail_resp is None:
            continue
        detail = BeautifulSoup(detail_resp.text, "html.parser")
        h1 = detail.find("h1")
        website_link = next(
            (
                a for a in detail.find_all("a", href=True)
                if a.get_text(strip=True).endswith("Opens in a new window.")
                and not _hostname_matches(a["href"], INDEX_VENTURES_EXCLUDED_DOMAINS)
            ),
            None,
        )
        if not h1 or not website_link:
            continue
        candidates.append({
            "name": h1.get_text(strip=True),
            "website": website_link["href"].strip(),
            "category": "startup",
            "source_note": "sourced via Index Ventures' public portfolio page",
        })
    return candidates


VC_LISTERS = {
    "balderton": balderton_candidates,
    "northzone": northzone_candidates,
    "accel": accel_candidates,
    "index_ventures": index_ventures_candidates,
}
