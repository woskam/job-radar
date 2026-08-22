# CLAUDE.md — Job Radar

Conventions and context for AI-assisted work on this repo. See `README.md` for what the project does and how to set it up.

## Philosophy

- Keep it light: no Docker, no heavy dependencies, designed to run comfortably on a Raspberry Pi. A headless browser (Playwright/Selenium) is a last resort for scraper discovery, not a recurring production dependency -- see the platform-detection notes in `companies.yaml` for cases where one might eventually be needed.
- Build and test new scrapers against saved HTML/JSON fixtures in `tests/sample_data/` first, not against live sites, before wiring them into `scheduler.py`.
- A single failing company/keyword combination must never crash the whole scrape cycle -- see `scheduler.py`'s `_safe_fetch()` wrapper, used around every live network call.

## Hard rules (do not relax these without being asked)

- **Never fabricate values that look like real credentials.** `.env` is filled in by the user by hand; never log its contents or commit it.
- **Never wire up live LinkedIn/Indeed scraping** without the user explicitly testing and approving that flow first.
- **Nothing gets sent automatically.** The letter generator only ever produces a draft (`letter_drafted` status); the user marks it `sent` themselves in the dashboard.
- **`DRY_RUN=true`** must mock every paid API call (Claude, and any real Telegram send) with placeholder behavior, so development never costs money or sends real notifications.
- Don't scrape a site whose owner is actively trying to block automated requests (WAF challenge, reCAPTCHA, rate-limiting) -- respect it and document it as blocked in `companies.yaml`, don't try to evade it.

## Config split

- `companies.yaml` — the shareable company/ATS database. Safe to commit, no personal data.
- `profile.yaml` — personal keywords, location preferences, scoring thresholds, and sender details. Gitignored; `profile.example.yaml` is the committed template.
- `matching/scorer.py::load_config()` merges both into one dict with the same shape the two used to have together in one file — every caller (`scheduler.py`, `approval_worker.py`, `dashboard/app.py`, tests) expects `config["companies"]`, `config["keywords"]`, `config["location"]`, `config["scoring"]` all on that one merged dict.

## Two independent cycles, on purpose

- `scheduler.py` (slow, every few hours via `job-radar.timer`): scrape → store → score → send Telegram approval requests. Does not process Telegram replies or generate letters.
- `approval_worker.py` (fast, ~90s via `job-radar-approvals.timer`): processes Telegram Approve/Reject replies, then generates + sends letters for anything now `approved` (via Telegram *or* the dashboard).

They're split deliberately: if both processed Telegram's `getUpdates` offset, they'd race on the same `app_state` row. Don't merge them back into one cycle without addressing that.

## Testing pattern

Before trusting any change to the scrape/score/letter pipeline, run a dry-run against a **scratch copy** of the database (never the live one), e.g.:

```bash
cp db/job_radar.db /tmp/scratch.db
JOB_RADAR_DB_PATH=/tmp/scratch.db DRY_RUN=true SCRAPE_LIVE=false ./venv/bin/python scheduler.py
```

and check the resulting counts/statuses before touching the real database or systemd units.
