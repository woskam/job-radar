# Job Radar

An automated job-vacancy monitor and cover-letter drafting assistant, designed to run unattended on something as small as a Raspberry Pi.

## What it does

- Scrapes job postings from 100+ pre-configured companies (`companies.yaml`) on a schedule, using each company's actual careers-site API rather than a generic browser-based crawler.
- Scores every posting against your own keywords, location preferences and exclusions (`profile.yaml`, kept out of version control).
- Sends you a Telegram message with **Approve**/**Reject** buttons for every match above your threshold -- nothing costs an API call until you say yes.
- On approval, generates a personalized cover-letter draft (Claude API) from your CV and project history, detects the job posting's language, and writes the letter (and picks your CV) in that language.
- Sends the finished draft back to you on Telegram, and keeps a local dashboard where you can review, edit, and download it as `.docx`/`.pdf` (with a letterhead) -- in three font choices.
- The same dashboard also generates a downloadable CV -- a full-length version and a condensed one-page version, both with the same letterhead/font choices, in English and (optionally) Dutch.
- **Nothing is ever sent automatically.** A letter sits in `letter_drafted` status until you mark it `sent` yourself, by hand, in the dashboard.

## Architecture

```
job-radar/
├── companies.yaml            # shareable database of companies + their ATS platform config
├── profile.example.yaml      # template -- copy to profile.yaml (gitignored) and fill in your own
├── .env.example               # template -- copy to .env (gitignored) and fill in your API keys
├── setup_wizard.py            # interactive first-time setup: .env, profile.yaml, CV/projects
├── add_company.py             # point it at a career page, it detects the ATS and tests it live
├── scheduler.py              # slow cycle (every few hours): scrape -> score -> send approval requests
├── approval_worker.py        # fast cycle (~90s): process Telegram replies -> generate + send letters
├── scrapers/                 # one small module per ATS platform (Workday, Greenhouse, Ashby, ...)
├── matching/
│   └── scorer.py             # keyword/location scoring, loads + merges companies.yaml + profile.yaml
├── letters/
│   ├── generator.py          # builds the Claude prompt, detects language, generates the draft
│   ├── document_style.py     # shared letterhead (header/footer/fonts) for every downloadable document
│   ├── cv_builder.py         # renders cv.txt into a letterhead-styled .docx/.pdf
│   ├── cv_short_builder.py   # renders cv_short.yaml into a one-page .docx/.pdf resume
│   ├── cv.example.txt        # template -- copy to cv.txt (and optionally cv_nl.txt) (gitignored)
│   ├── cv_short.example.yaml # template -- copy to cv_short.yaml (and optionally cv_short_nl.yaml) (gitignored)
│   ├── projects.example.json # template -- copy to projects.json (gitignored)
│   └── example_cover_letter.txt  # optional: a sample of your own writing style/tone (gitignored)
├── notify/
│   └── telegram_bot.py        # sendMessage/getUpdates wrappers, approval-request + letter delivery
├── dashboard/
│   ├── app.py                 # Flask app: job list, letter editor, status actions, .docx/.pdf export, CV downloads
│   └── templates/
├── db/
│   ├── schema.sql
│   └── migrations.py          # lightweight additive column migrations
└── tests/
    └── sample_data/           # saved HTML/JSON fixtures for dry-run testing
```

## Setup

**Quick path:** after step 1 below, run `python setup_wizard.py` -- it walks
you through `.env`, `profile.yaml`, and your CV/projects interactively
(including validating your API keys live, and optionally having Claude turn
pasted raw CV text into the right format), instead of the manual copy+edit
steps below. The steps below are what it does under the hood, and how to do
each one by hand if you'd rather.

1. `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
2. `cp .env.example .env` and fill in `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Leave `DRY_RUN=true` and `SCRAPE_LIVE=false` for now.
3. `cp profile.example.yaml profile.yaml` and edit your keywords, location, scoring preferences and sender details.
4. `cp letters/cv.example.txt letters/cv.txt` and write your real CV. If you want letters written in Dutch too, also add `letters/cv_nl.txt` (optional -- falls back to the English CV if missing).
5. `cp letters/projects.example.json letters/projects.json` and describe 2-4 of your own projects -- the generator picks the 2-3 most relevant ones per job based on tag overlap with the posting.
6. Optionally `cp letters/cv_short.example.yaml letters/cv_short.yaml` and fill in the one-page version of your CV (and `letters/cv_short_nl.yaml` for Dutch) -- lets you download a condensed resume from the dashboard's CV page alongside the full-length one.
7. Optionally add `letters/example_cover_letter.txt`, a letter you've written yourself, as a tone/style reference for the generator.
8. Dry-run everything first: `./run.sh` then `./run_approvals.sh` -- with `DRY_RUN=true` this mocks the Claude API and Telegram sends, so nothing costs anything or reaches your phone yet.
9. Once you're happy, set `DRY_RUN=false` and `SCRAPE_LIVE=true` in `.env` and run again for real.
10. Install the systemd units for unattended operation: `cp job-radar.service.example job-radar.service` (and the same for `job-radar-approvals.service`), edit the `WorkingDirectory`/`ExecStart` paths to your actual install path, then:
    ```
    sudo cp job-radar*.service job-radar*.timer /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now job-radar.timer job-radar-approvals.timer
    ```
11. Run the dashboard: `python dashboard/app.py`, open `http://localhost:5000`.

## Adding your own keywords

Edit `profile.yaml`'s `keywords` list. Add `keyword_weights` for any keyword that's too generic on its own (e.g. a bare "manager" matches a lot of unrelated roles) -- a weight below 1.0 stops that keyword alone from clearing the score threshold. `location.bonus_cities` controls which cities count as "home turf", and `scoring.exclude_title_keywords` always rejects a title regardless of score (useful for excluding internships, etc.).

## Adding a new company

**Quick path:** `python add_company.py <career-page-url>` -- it checks the
page against every ATS platform already supported below, and if it
recognizes one, live-tests it and offers to append a working entry to
`companies.yaml` for you. See `CONTRIBUTING.md` for what to do if it doesn't
recognize the platform.

By hand: add an entry to `companies.yaml`'s `companies:` list. The `ats` field determines which scraper module gets reused, and which extra fields that company's entry needs:

| `ats` value | Extra fields needed | Scraper module |
|---|---|---|
| `workday` | `workday_host`, `workday_site` | `scrapers/workday_scraper.py` |
| `sap_successfactors` | `successfactors_base_url` | `scrapers/successfactors_scraper.py` |
| `radancy` | `radancy_base_url` (+ optional `radancy_path` for a tenant-specific pre-filtered location page) | `scrapers/radancy_scraper.py` |
| `dropr` | `dropr_base_url` | `scrapers/dropr_scraper.py` |
| `google` | -- (fixed endpoint, reverse-engineered internal format) | `scrapers/google_scraper.py` |
| `smartrecruiters` | `smartrecruiters_company_id` | `scrapers/smartrecruiters_scraper.py` |
| `eightfold` | `eightfold_base_url`, `eightfold_domain` | `scrapers/eightfold_scraper.py` |
| `phenom` | `phenom_base_url` | `scrapers/phenom_scraper.py` |
| `oracle_recruiting_cloud` | `oracle_host`, `oracle_site_number` | `scrapers/oracle_scraper.py` |
| `greenhouse` | `greenhouse_board_token` | `scrapers/greenhouse_scraper.py` |
| `ashby` | `ashby_board_token` | `scrapers/ashby_scraper.py` |
| `jobylon` | `jobylon_base_url` | `scrapers/jobylon_scraper.py` |
| `homerun` | `homerun_feed_slug` | `scrapers/homerun_scraper.py` |
| `brassring` | `brassring_partner_id`, `brassring_site_id` | `scrapers/brassring_scraper.py` |
| `recruitee` | `recruitee_company_slug` | `scrapers/recruitee_scraper.py` |
| `deel` | `deel_company_slug` | `scrapers/deel_scraper.py` |
| `getnoticed` | `getnoticed_base_url` | `scrapers/getnoticed_scraper.py` |
| `custom` | -- (no shared platform found) | needs its own `scrapers/{company}_scraper.py`, wired into `scheduler.py` |

Add `remote_friendly: true` to a company that's genuinely all-remote (hires anywhere, e.g. GitLab) -- the scorer then won't penalize a "Remote, &lt;country&gt;" location as being abroad, unlike for companies where that phrasing really does mean domestic-only remote work.

Most `ats` values were found by fetching the company's careers page and looking for the platform's fingerprint in the raw HTML (e.g. `myworkdayjobs.com`, `boards-api.greenhouse.io`, `jobs.ashbyhq.com`, an embedded `__NUXT__`/`__NEXT_DATA__` blob, a `data-jibe-search-version` attribute for iCIMS/Jibe) -- see the `note:` field on existing entries for the reasoning behind each one, including the ones that turned out to be blocked or not (yet) solvable without a headless browser.

## Safety defaults (please keep these)

- **Live LinkedIn/Indeed scraping is intentionally not wired up.** Build and test against saved HTML samples in `tests/sample_data/` first if you ever want to add it, and only enable it once you've reviewed the login flow yourself.
- **Nothing is ever sent automatically.** The letter generator only ever produces a draft; you mark it `sent` yourself, by hand, in the dashboard.
- **`DRY_RUN=true`** mocks the Claude API call and Telegram sends with placeholder text, so you can develop and test without incurring costs or noise on your phone.
- Never commit `.env`, `profile.yaml`, your CV (`cv.txt`/`cv_nl.txt`/`cv_short.yaml`/`cv_short_nl.yaml`), or `letters/projects.json` -- see `.gitignore`.

## Contributing

See `CONTRIBUTING.md` -- the short version: run `python add_company.py <career-page-url>` to add a company, most other files are personal/gitignored and shouldn't need a PR.

## License

MIT -- see `LICENSE`.
