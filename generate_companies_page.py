#!/usr/bin/env python3
"""
Renders companies.yaml into a plain static HTML table for job-radar-site's
public companies page -- purely informational (name, category, segment,
a link to the careers page), no search/filter JS, matching the rest of
that site's plain-HTML style. Re-run and copy the output into
job-radar-site whenever companies.yaml changes meaningfully; not wired
into any automated pipeline.

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
  <link rel="canonical" href="https://job-radar-c66.pages.dev/companies">
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
    <p class="tagline">{count} companies Job Radar tracks for job listings, from large employers to startups and scale-ups.</p>

    <table>
      <tr><th>Company</th><th>Category</th><th>Segment</th></tr>
{rows}
    </table>
  </div>
</body>
</html>
"""

ROW_TEMPLATE = '      <tr><td><a href="{url}">{name}</a></td><td>{category}</td><td>{segment}</td></tr>'


def render(companies: list[dict]) -> str:
    companies = sorted(companies, key=lambda c: c["name"].lower())
    rows = []
    for c in companies:
        rows.append(ROW_TEMPLATE.format(
            url=escape(c["career_url"], quote=True),
            name=escape(c["name"]),
            category=escape(c.get("category", "")),
            segment=escape(c.get("segment", "")),
        ))
    return TEMPLATE.format(count=len(companies), rows="\n".join(rows))


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
