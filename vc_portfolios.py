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

    - sequoia (sequoiacap.com/our-companies/): only 21 curated "greatest
      hits" links to ./companies/<slug> (SpaceX, Airbnb, Nvidia, Apple,
      Google, Stripe, ...), not the full portfolio -- Sequoia's own site
      never exposes the rest in raw HTML, so this stays a small, partial
      list by design, not something a smarter parser would fix. Kept
      anyway since 21 extra fetches is cheap; the net new-company yield
      is expected to be low since most of these are already-huge, already
      -covered names. Each ./companies/<slug> page's <h1> gives the name
      and the first external link outside sequoiacap.com/linkedin.com/
      x.com/twitter.com gives the real site.

    - eqt_ventures (eqtgroup.com, the fund-filtered "browse all
      companies" URL -- /about/current-portfolio?fund=eqt_ventures_i,
      eqt_ventures_ii,eqt_ventures_iii): only 25 unique companies in raw
      HTML (1X, AnyDesk, Anyfin, Codacy, Einride, Fly.io, ...), clearly
      the first alphabetical batch (1x..f) -- the rest sits behind
      client-side infinite-scroll a plain GET can't reach, so like
      Sequoia this is a partial, first-batch-only list, not a bug to fix
      later. Each /about/current-portfolio/<slug> detail page's <h1>
      gives the name and the first external link outside eqtgroup.com/
      linkedin.com/x.com/twitter.com/youtube.com/instagram.com/
      facebook.com gives the real site.

    - antler (antler.co/portfolio): Webflow CMS + FinSweet CMS Filter,
      the richest listing of any VC here -- every div.portco_card already
      carries name, sector, country, AND the real external website with
      no detail-page hop at all. Country comes from the first tag's own
      fs-cmsfilter-field attribute (e.g. fs-cmsfilter-field="UK"), sector
      from the second tag. Paginated the same way as northzone
      (?<hash>_page=N), confirmed live across 21 pages / 1081 cards
      (2026-09-30). Requested specifically for European coverage --
      antler.co/location/<country> pages exist but only show a small
      ~11-company "featured" carousel with no pagination, so the country
      filter is applied in Python against the full paginated /portfolio
      listing instead (ANTLER_EUROPE_COUNTRIES), not via that URL.

      Deliberately built against antler.co directly rather than the
      third-party GitHub mirror yc-oss-style repos exist for (e.g.
      yigitmeteozcan/startups, MIT-licensed, which also covers Antler
      plus Techstars/Plug and Play/500 Global/Alchemist/Entrepreneur
      First) -- confirmed with Wychert: for something feeding a
      commercial product, go to each accelerator's own public page
      directly, same as every other VC lister here, not through an
      unofficial aggregator of unclear provenance for the underlying
      data. The mirror's count (1079) lined up closely with this
      first-party count (1081), which was a useful cross-check but not a
      reason to depend on it.

  SKIPPED (JS-rendered / image-carousel, no data in raw HTML -- confirmed
  with Wychert, not worth a headless browser per CLAUDE.md's "last resort,
  not a recurring dependency"):
    - a16z (a16z.com/portfolio): image carousel, no links/JSON in raw HTML.
    - Atomico (atomico.com/portfolio): HTTP 429 on first request --
      treated as rate-limiting, not pushed further.
    - Lakestar (lakestar.com/portfolio): logo images only, no links.
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
SEQUOIA_URL = "https://www.sequoiacap.com/our-companies/"
EQT_VENTURES_URL = "https://eqtgroup.com/about/current-portfolio?fund=eqt_ventures_i%2ceqt_ventures_ii%2ceqt_ventures_iii"
ANTLER_URL = "https://www.antler.co/portfolio"

INDEX_VENTURES_EXCLUDED_DOMAINS = ("indexventures.com", "x.com", "twitter.com", "linkedin.com", "notoptional.eu")
SEQUOIA_EXCLUDED_DOMAINS = ("sequoiacap.com", "linkedin.com", "x.com", "twitter.com")
EQT_VENTURES_EXCLUDED_DOMAINS = ("eqtgroup.com", "linkedin.com", "x.com", "twitter.com", "youtube.com", "instagram.com", "facebook.com")

# Country names as they appear in Antler's own fs-cmsfilter-field tags
# (confirmed live: "UK" not "United Kingdom", "Netherlands" not "The
# Netherlands", ...). Includes a few plausible European countries never
# seen in the live sample (2026-09-30), so a future refresh doesn't
# silently miss them if Antler adds a cohort there.
ANTLER_EUROPE_COUNTRIES = {
    "UK", "Germany", "France", "Netherlands", "Sweden", "Norway", "Denmark",
    "Finland", "Portugal", "Spain", "Ireland", "Belgium", "Italy", "Poland",
    "Austria", "Switzerland",
}


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


def sequoia_candidates() -> list[dict]:
    resp = fetch(SEQUOIA_URL)
    if resp is None:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    # (slug, name) from the listing page itself -- the detail page has no
    # <h1> and its <h2>s are section headers ("Milestones", "Team", ...),
    # not the company name, so the name is captured here instead, from the
    # <h2> inside each card link (confirmed live: "SpaceX" for spacex).
    rows: list[tuple[str, str]] = []
    seen_slugs = set()
    for link in soup.select('a[href^="./companies/"]'):
        slug = link.get("href", "").removeprefix("./companies/").strip("/")
        name_el = link.find("h2")
        if slug and name_el and slug not in seen_slugs:
            seen_slugs.add(slug)
            rows.append((slug, name_el.get_text(strip=True)))

    candidates = []
    for slug, name in rows:
        time.sleep(DETAIL_FETCH_DELAY)
        detail_resp = fetch(f"https://www.sequoiacap.com/companies/{slug}")
        if detail_resp is None:
            continue
        detail = BeautifulSoup(detail_resp.text, "html.parser")
        website_link = next(
            (
                a for a in detail.find_all("a", href=True)
                if a["href"].startswith("http") and not _hostname_matches(a["href"], SEQUOIA_EXCLUDED_DOMAINS)
            ),
            None,
        )
        if not website_link:
            continue
        candidates.append({
            "name": name,
            "website": website_link["href"].strip(),
            "category": "startup",
            "source_note": "sourced via Sequoia Capital's public portfolio page (a curated subset, not the full portfolio)",
        })
    return candidates


def eqt_ventures_candidates() -> list[dict]:
    resp = fetch(EQT_VENTURES_URL)
    if resp is None:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    slugs = []
    seen_slugs = set()
    for link in soup.select('a[href^="/about/current-portfolio/"]'):
        href = link.get("href", "")
        slug = href.removeprefix("/about/current-portfolio/").split("?")[0].strip("/")
        if not slug or "/" in slug or slug in ("funds", "divestments"):
            continue
        if slug not in seen_slugs:
            seen_slugs.add(slug)
            slugs.append(slug)

    candidates = []
    for slug in slugs:
        time.sleep(DETAIL_FETCH_DELAY)
        detail_resp = fetch(f"https://eqtgroup.com/about/current-portfolio/{slug}")
        if detail_resp is None:
            continue
        detail = BeautifulSoup(detail_resp.text, "html.parser")
        h1 = detail.find("h1")
        website_link = next(
            (
                a for a in detail.find_all("a", href=True)
                if a["href"].startswith("http") and not _hostname_matches(a["href"], EQT_VENTURES_EXCLUDED_DOMAINS)
            ),
            None,
        )
        if not h1 or not website_link:
            continue
        candidates.append({
            "name": h1.get_text(strip=True),
            "website": website_link["href"].strip(),
            "category": "startup",
            "source_note": "sourced via EQT Ventures' public portfolio page (first alphabetical batch only, not the full portfolio)",
        })
    return candidates


def _antler_category(sector: str | None) -> str:
    if not sector:
        return "startup"
    return sector.strip().lower().replace(" ", "_").replace("/", "_")


def _antler_all_candidates() -> list[dict]:
    """Every Antler portfolio company, any country -- paginates the full
    /portfolio listing (see antler_candidates/antler_rest_candidates for
    the country-filtered views actually registered in VC_LISTERS)."""
    candidates = []
    url = ANTLER_URL
    while url:
        resp = fetch(url)
        if resp is None:
            break
        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.select("div.portco_card"):
            name_el = card.select_one('[fs-cmsfilter-field="name"]')
            tags = card.select(".portco_card_tags .tag_small_wrap")
            website_link = card.select_one("a.clickable_link")
            if not name_el or not tags or not website_link or not website_link.get("href"):
                continue

            country = tags[0].get("fs-cmsfilter-field")
            sector = tags[1].get_text(strip=True) if len(tags) > 1 else None

            candidates.append({
                "name": name_el.get_text(strip=True),
                "website": website_link["href"].strip(),
                "category": _antler_category(sector),
                "country": country,
                "source_note": f"sourced via Antler's public portfolio page (country: {country or 'unspecified'})",
            })

        next_link = soup.select_one(".w-pagination-next")
        url = f"{ANTLER_URL}{next_link['href']}" if next_link and next_link.get("href") else None
        if url:
            time.sleep(DETAIL_FETCH_DELAY)
    return candidates


def _drop_country_field(candidates: list[dict]) -> list[dict]:
    # "country" is only carried internally to filter on -- the shared
    # candidate shape run_bulk/build_entry expect is name/website/
    # category/source_note, same as every other VC lister.
    return [{k: v for k, v in c.items() if k != "country"} for c in candidates]


def antler_candidates() -> list[dict]:
    all_candidates = _antler_all_candidates()
    return _drop_country_field([c for c in all_candidates if c["country"] in ANTLER_EUROPE_COUNTRIES])


def antler_rest_candidates() -> list[dict]:
    """Every Antler company NOT in ANTLER_EUROPE_COUNTRIES -- the "antler"
    lister already covers Europe (run and merged 2026-09-30); this is the
    rest of the world, same source, same pipeline, just the complement of
    that country filter."""
    all_candidates = _antler_all_candidates()
    return _drop_country_field([c for c in all_candidates if c["country"] not in ANTLER_EUROPE_COUNTRIES])


VC_LISTERS = {
    "balderton": balderton_candidates,
    "northzone": northzone_candidates,
    "accel": accel_candidates,
    "index_ventures": index_ventures_candidates,
    "sequoia": sequoia_candidates,
    "eqt_ventures": eqt_ventures_candidates,
    "antler": antler_candidates,
    "antler_rest": antler_rest_candidates,
}
