# Contributing

The main thing worth contributing here is `companies.yaml` -- more companies
means more people get useful matches. Everything else (`profile.yaml`, your
CV, `letters/projects.json`, `.env`) is personal and gitignored, so a PR
should almost never need to touch anything outside `companies.yaml` (and
occasionally a new `scrapers/*.py` module, if you've found a genuinely new
platform).

## Adding a company

1. Try `python add_company.py <career-page-url>` first. It checks the page
   against the ATS platforms already supported in `scrapers/`, and if it
   recognizes one, live-tests it and offers to append a working
   `companies.yaml` entry for you -- no need to read any of this codebase
   to use it.
2. If it doesn't recognize the platform, it prints what it found in the raw
   HTML (any embedded script hosts, API-looking URLs). Cross-reference that
   against the `ats` table in `README.md`'s "Adding a new company" section --
   you may be looking at a platform this project already supports under a
   name the detector doesn't check for yet.
3. If it's genuinely a new platform, that needs a new `scrapers/*_scraper.py`
   module. Build and test it against a saved HTML/JSON fixture in
   `tests/sample_data/` first (see any existing `test_*_scraper.py` for the
   pattern), not against the live site repeatedly -- then wire it into
   `scheduler.py`.
4. If the site actively blocks automated requests (a CAPTCHA, a WAF
   challenge, aggressive rate-limiting), don't try to work around it --
   `add_company.py` will tell you this and skip it. Document it as blocked
   in `companies.yaml` with a `note:` explaining what you saw, same as the
   existing blocked entries there.

## Before opening a PR

- Run the existing tests: `./venv/bin/python tests/test_<whatever>.py` for
  anything you touched (each is a standalone script, not a pytest suite).
- Do a dry-run regression against a **scratch copy** of a database (never
  commit a real `db/job_radar.db`), e.g.:
  ```bash
  cp db/job_radar.db /tmp/scratch.db   # or start from an empty one --
                                        # db/schema.sql creates the tables
  JOB_RADAR_DB_PATH=/tmp/scratch.db DRY_RUN=true SCRAPE_LIVE=true ./venv/bin/python scheduler.py
  ```
  and confirm your new company shows up with real postings and no
  tracebacks.
- Keep `companies.yaml` entries in the existing shape: `name`, `category`,
  `career_url`, `ats` + that platform's specific fields, and a `note:`
  whenever there's anything non-obvious about how you found or verified it
  (see any existing entry for the convention). Add `segment: "startup"` if
  the company was sourced from a VC portfolio rather than picked as an
  established employer -- see `bulk_add_from_yc.py` for the bulk version of
  this same workflow, used for YCombinator's directory.
