#!/usr/bin/env python3
"""
Renders companies.yaml into a static HTML table for job-radar-site's
public companies page -- name, category, segment, a link to the careers
page, with plain vanilla-JS client-side filtering (search text, segment,
category) baked in. No framework, no server calls: the whole company list
is already in the page, filtering just shows/hides rows. Re-run and copy
the output into job-radar-site whenever companies.yaml changes
meaningfully; not wired into any automated pipeline.

Usage: python generate_companies_page.py [output_path]
(default: prints to stdout)
"""
import sys
from html import escape
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
COMPANIES_PATH = ROOT / "companies.yaml"

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Job Radar Companies</title>
  <meta name="description" content="Companies Job Radar tracks for job listings.">
  <link rel="canonical" href="https://12getajob.com/companies">
  <link rel="stylesheet" href="/assets/style.css">
  <script type="module" src="/assets/analytics.js"></script>
</head>
<body>
  <div class="wrap">
    <header class="site-header">
      <a href="/">Job Radar</a>
      <nav>
        <a href="/companies">Companies</a>
        <a href="/api">API docs</a>
        <a href="https://github.com/woskam/job-radar">Open source</a>
        <a href="https://github.com/woskam/job-radar-hub">Hub source</a>
      </nav>
    </header>

    <h1>Companies</h1>
    <p class="tagline"><span id="count">{count}</span> of {count} companies Job Radar tracks for job listings, from large employers to startups and scale-ups.</p>

    <div class="filters">
      <input type="search" id="q" placeholder="Search company or category&hellip;">
      <select id="segment-filter">
        <option value="">All segments</option>
        <option value="startup">Startups &amp; scale-ups</option>
        <option value="__established__">Established</option>
      </select>
      <select id="category-filter">
        <option value="">All categories</option>
{category_options}
      </select>
    </div>

    <table id="companies-table">
      <tr><th>Company</th><th>Category</th><th>Segment</th></tr>
{rows}
    </table>
  </div>

  <script>
    const rows = Array.from(document.querySelectorAll('#companies-table tr[data-name]'));
    const countEl = document.getElementById('count');
    const q = document.getElementById('q');
    const segmentFilter = document.getElementById('segment-filter');
    const categoryFilter = document.getElementById('category-filter');

    function applyFilters() {{
      const term = q.value.trim().toLowerCase();
      const segment = segmentFilter.value;
      const category = categoryFilter.value;
      let shown = 0;
      for (const row of rows) {{
        const matchesTerm = !term || row.dataset.name.includes(term) || row.dataset.category.includes(term);
        const matchesSegment = !segment
          || (segment === '__established__' ? !row.dataset.segment : row.dataset.segment === segment);
        const matchesCategory = !category || row.dataset.category === category;
        const visible = matchesTerm && matchesSegment && matchesCategory;
        row.hidden = !visible;
        if (visible) shown++;
      }}
      countEl.textContent = shown;
    }}

    q.addEventListener('input', applyFilters);
    segmentFilter.addEventListener('change', applyFilters);
    categoryFilter.addEventListener('change', applyFilters);
  </script>
</body>
</html>
"""

ROW_TEMPLATE = (
    '      <tr data-name="{name_attr}" data-category="{category_attr}" data-segment="{segment_attr}">'
    '<td><a href="{url}">{name}</a></td><td>{category}</td><td>{segment}</td></tr>'
)


def render(companies: list[dict]) -> str:
    companies = sorted(companies, key=lambda c: c["name"].lower())
    categories = sorted({c["category"] for c in companies if c.get("category")})

    rows = []
    for c in companies:
        category = c.get("category", "")
        segment = c.get("segment", "")
        rows.append(ROW_TEMPLATE.format(
            url=escape(c["career_url"], quote=True),
            name=escape(c["name"]),
            category=escape(category),
            segment=escape(segment),
            name_attr=escape(c["name"].lower(), quote=True),
            category_attr=escape(category.lower(), quote=True),
            segment_attr=escape(segment, quote=True),
        ))

    category_options = "\n".join(
        f'        <option value="{escape(cat, quote=True)}">{escape(cat)}</option>' for cat in categories
    )

    return TEMPLATE.format(
        count=len(companies),
        rows="\n".join(rows),
        category_options=category_options,
    )


def main() -> None:
    with open(COMPANIES_PATH) as f:
        data = yaml.safe_load(f)

    html = render(data["companies"])

    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(html)
        print(f"Wrote {sys.argv[1]}")
    else:
        print(html)


if __name__ == "__main__":
    main()
