#!/usr/bin/env python3
"""
Extracts just the company names out of companies.yaml into a plain JS
array for job-radar-site's assets/companies.js -- the client-side
autocomplete list for the /jobs search page's Company field. Same
"re-run and copy into job-radar-site whenever companies.yaml changes"
workflow as generate_companies_page.py, not wired into any pipeline.

Usage: python generate_companies_list_js.py [output_path]
(default: prints to stdout)
"""
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
COMPANIES_PATH = ROOT / "companies.yaml"

HEADER = (
    "// Company names for the /jobs search page's Company field autocomplete --\n"
    "// generated from companies.yaml by generate_companies_list_js.py, re-run and\n"
    "// copied in here whenever companies.yaml changes meaningfully (same workflow\n"
    "// as companies.html/generate_companies_page.py). Includes every tracked\n"
    "// company regardless of current scrape/listing status -- same \"might suggest\n"
    "// a company with zero active listings right now\" trade-off GET /jobs'\n"
    "// company filter already has (see job-radar-hub's db/queries.py).\n"
    "export const COMPANIES = "
)


def main() -> None:
    with open(COMPANIES_PATH) as f:
        data = yaml.safe_load(f)

    names = sorted({c["name"] for c in data["companies"] if c.get("name")}, key=str.casefold)
    js = HEADER + json.dumps(names, ensure_ascii=False) + ";\n"

    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(js)
        print(f"Wrote {sys.argv[1]} ({len(names)} companies)")
    else:
        print(js)


if __name__ == "__main__":
    main()
