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

  SKIPPED (JS-rendered / image-carousel, no data in raw HTML -- confirmed
  with Wychert, not worth a headless browser per CLAUDE.md's "last resort,
  not a recurring dependency"):
    - a16z (a16z.com/portfolio): image carousel, no links/JSON in raw HTML.
    - Atomico (atomico.com/portfolio): HTTP 429 on first request --
      treated as rate-limiting, not pushed further.
    - Lakestar (lakestar.com/portfolio): logo images only, no links.

  SCOPED, NOT YET BUILT (confirmed static HTML exists, but each needs its
  own parser + an extra hop to find the real external site -- same shape
  of work as `balderton_candidates` took, just not done yet):
    - Northzone (northzone.com/portfolio): Webflow CMS, card only links to
      an internal /portfolio/<slug> detail page.
    - Accel (accel.com/companies): ~150+ companies visible unpaginated,
      but only internal /companies/<slug> links.
    - Sequoia Capital (sequoiacap.com/our-companies): only ~21 curated
      companies in raw HTML (not the full portfolio), internal links only.
    - Index Ventures (indexventures.com/companies): ~500 companies, but
      only internal /companies/<slug> links.
    - EQT Ventures (eqtgroup.com/private-capital/eqt-ventures): front page
      only shows 5 featured companies; full list is behind a "See all"
      filtered URL not yet inspected.
"""
from bs4 import BeautifulSoup

from add_company import fetch

BALDERTON_URL = "https://www.balderton.com/companies/"


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


VC_LISTERS = {
    "balderton": balderton_candidates,
}
