import os
import sqlite3
from pathlib import Path

import requests
from dotenv import load_dotenv

from db.migrations import ensure_columns
from matching.scorer import load_config, score_jobs
from notify.telegram_bot import build_approval_request_text, send_approval_request
from scrapers.company_pages import parse_company_page
from scrapers.indeed_scraper import parse_search_results as parse_indeed
from scrapers.linkedin_scraper import parse_search_results as parse_linkedin
from scrapers.ashby_scraper import fetch_live_search as fetch_ashby
from scrapers.avature_scraper import fetch_live_search as fetch_avature
from scrapers.brassring_scraper import fetch_live_search as fetch_brassring
from scrapers.deel_scraper import fetch_live_search as fetch_deel
from scrapers.dropr_scraper import fetch_live_search as fetch_dropr
from scrapers.eightfold_scraper import fetch_live_search as fetch_eightfold
from scrapers.getnoticed_scraper import fetch_live_search as fetch_getnoticed
from scrapers.google_scraper import fetch_live_search as fetch_google
from scrapers.greenhouse_scraper import fetch_live_search as fetch_greenhouse
from scrapers.homerun_scraper import fetch_live_search as fetch_homerun
from scrapers.jobylon_scraper import fetch_live_search as fetch_jobylon
from scrapers.mollie_scraper import fetch_live_search as fetch_mollie
from scrapers.oracle_scraper import fetch_live_search as fetch_oracle
from scrapers.phenom_scraper import fetch_live_search as fetch_phenom
from scrapers.radancy_scraper import fetch_live_search as fetch_radancy
from scrapers.recruitee_scraper import fetch_live_search as fetch_recruitee
from scrapers.smartrecruiters_scraper import fetch_live_search as fetch_smartrecruiters
from scrapers.successfactors_scraper import fetch_live_search as fetch_successfactors
from scrapers.tsf_scraper import fetch_live_search as fetch_tsf
from scrapers.uwv_scraper import fetch_live_search as fetch_uwv
from scrapers.vodafoneziggo_scraper import fetch_live_search as fetch_vodafoneziggo
from scrapers.wba_scraper import fetch_live_search as fetch_wba
from scrapers.werkenvoornederland_scraper import fetch_live_search as fetch_wvn
from scrapers.workday_scraper import fetch_live_search as fetch_workday
from scrapers.workday_scraper import parse_search_results as parse_workday

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("JOB_RADAR_DB_PATH", ROOT / "db" / "job_radar.db"))
SCHEMA_PATH = ROOT / "db" / "schema.sql"
SAMPLE_DIR = ROOT / "tests" / "sample_data"


def _safe_fetch(label: str, fn, **kwargs):
    # A single slow/temporarily unreachable ATS host must never crash the whole
    # scrape cycle -- a timeout on one company/keyword combination used to take
    # down the entire run (see the Nike Workday incident, 15:00 run). Skip just
    # that one combination instead of dragging the rest of the ~20 platforms
    # down with it.
    try:
        return fn(**kwargs)
    except requests.exceptions.RequestException as exc:
        print(f"[scrape] {label} skipped due to a network error: {exc}")
        return None


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_PATH.read_text())
    ensure_columns(conn)
    return conn


def scrape_workday_live(config: dict) -> list[dict]:
    # Workday's searchText apparently does AND-matching across all the words
    # together, so looking up all keywords at once returns almost nothing.
    # Searching per keyword and deduping on external_id works well (tested:
    # PVH -> "director digital" immediately found Amsterdam roles).
    jobs_by_key: dict[tuple[str, str], dict] = {}

    for company in config["companies"]:
        if company.get("ats") != "workday":
            continue
        for keyword in config["keywords"]:
            data = _safe_fetch(
                f"workday:{company['name']}:{keyword}",
                fetch_workday,
                host=company["workday_host"], site=company["workday_site"], search_text=keyword,
            )
            if data is None:
                continue
            for job in parse_workday(
                data, host=company["workday_host"], site=company["workday_site"], source=company["name"]
            ):
                jobs_by_key[(job["source"], job["external_id"])] = job

    return list(jobs_by_key.values())


def scrape_successfactors_live(config: dict) -> list[dict]:
    jobs_by_key: dict[tuple[str, str], dict] = {}

    for company in config["companies"]:
        base_url = company.get("successfactors_base_url")
        if not base_url:
            continue
        for keyword in config["keywords"]:
            jobs = _safe_fetch(
                f"successfactors:{company['name']}:{keyword}",
                fetch_successfactors, base_url=base_url, source=company["name"], keywords=keyword,
            )
            for job in jobs or []:
                jobs_by_key[(job["source"], job["external_id"])] = job

    return list(jobs_by_key.values())


def scrape_radancy_live(config: dict) -> list[dict]:
    jobs_by_key: dict[tuple[str, str], dict] = {}

    for company in config["companies"]:
        base_url = company.get("radancy_base_url")
        if not base_url:
            continue
        # Some tenants (Citi) silently ignore the l=<location> search param
        # and require a tenant-specific pre-filtered location page instead --
        # fetched once (already scoped, no k/l params), not per-keyword.
        radancy_path = company.get("radancy_path")
        if radancy_path:
            jobs = _safe_fetch(
                f"radancy:{company['name']}:{radancy_path}",
                fetch_radancy, base_url=base_url, source=company["name"], path=radancy_path,
            )
            for job in jobs or []:
                jobs_by_key[(job["source"], job["external_id"])] = job
            continue
        for keyword in config["keywords"]:
            jobs = _safe_fetch(
                f"radancy:{company['name']}:{keyword}",
                fetch_radancy, base_url=base_url, source=company["name"], keywords=keyword, location="Netherlands",
            )
            for job in jobs or []:
                jobs_by_key[(job["source"], job["external_id"])] = job

    return list(jobs_by_key.values())


def scrape_dropr_live(config: dict) -> list[dict]:
    jobs_by_key: dict[tuple[str, str], dict] = {}

    for company in config["companies"]:
        base_url = company.get("dropr_base_url")
        if not base_url:
            continue
        for keyword in config["keywords"]:
            jobs = _safe_fetch(
                f"dropr:{company['name']}:{keyword}",
                fetch_dropr, base_url=base_url, source=company["name"], keywords=keyword,
            )
            for job in jobs or []:
                jobs_by_key[(job["source"], job["external_id"])] = job

    return list(jobs_by_key.values())


def scrape_google_live(config: dict) -> list[dict]:
    jobs_by_key: dict[tuple[str, str], dict] = {}

    for company in config["companies"]:
        if company.get("ats") != "google":
            continue
        for keyword in config["keywords"]:
            jobs = _safe_fetch(
                f"google:{company['name']}:{keyword}",
                fetch_google, source=company["name"], keywords=keyword, location="Netherlands",
            )
            for job in jobs or []:
                jobs_by_key[(job["source"], job["external_id"])] = job

    return list(jobs_by_key.values())


def scrape_smartrecruiters_live(config: dict) -> list[dict]:
    jobs_by_key: dict[tuple[str, str], dict] = {}

    for company in config["companies"]:
        company_id = company.get("smartrecruiters_company_id")
        if not company_id:
            continue
        for keyword in config["keywords"]:
            jobs = _safe_fetch(
                f"smartrecruiters:{company['name']}:{keyword}",
                fetch_smartrecruiters, company_id=company_id, source=company["name"], keywords=keyword,
            )
            for job in jobs or []:
                jobs_by_key[(job["source"], job["external_id"])] = job

    return list(jobs_by_key.values())


def scrape_oracle_live(config: dict) -> list[dict]:
    jobs_by_key: dict[tuple[str, str], dict] = {}

    for company in config["companies"]:
        host = company.get("oracle_host")
        site_number = company.get("oracle_site_number")
        if not host or not site_number:
            continue
        for keyword in config["keywords"]:
            jobs = _safe_fetch(
                f"oracle:{company['name']}:{keyword}",
                fetch_oracle, host=host, site_number=site_number, source=company["name"], keyword=keyword,
            )
            for job in jobs or []:
                jobs_by_key[(job["source"], job["external_id"])] = job

    return list(jobs_by_key.values())


def scrape_eightfold_live(config: dict) -> list[dict]:
    jobs_by_key: dict[tuple[str, str], dict] = {}

    for company in config["companies"]:
        base_url = company.get("eightfold_base_url")
        domain = company.get("eightfold_domain")
        if not base_url or not domain:
            continue
        for keyword in config["keywords"]:
            jobs = _safe_fetch(
                f"eightfold:{company['name']}:{keyword}",
                fetch_eightfold, base_url=base_url, domain=domain, source=company["name"], query=keyword,
            )
            for job in jobs or []:
                jobs_by_key[(job["source"], job["external_id"])] = job

    return list(jobs_by_key.values())


def scrape_avature_live(config: dict) -> list[dict]:
    jobs_by_key: dict[tuple[str, str], dict] = {}

    for company in config["companies"]:
        base_url = company.get("avature_base_url")
        if not base_url:
            continue
        for keyword in config["keywords"]:
            jobs = _safe_fetch(
                f"avature:{company['name']}:{keyword}",
                fetch_avature, base_url=base_url, source=company["name"], keywords=keyword,
            )
            for job in jobs or []:
                jobs_by_key[(job["source"], job["external_id"])] = job

    return list(jobs_by_key.values())


def scrape_phenom_live(config: dict) -> list[dict]:
    jobs_by_key: dict[tuple[str, str], dict] = {}

    for company in config["companies"]:
        base_url = company.get("phenom_base_url")
        if not base_url:
            continue
        for keyword in config["keywords"]:
            jobs = _safe_fetch(
                f"phenom:{company['name']}:{keyword}",
                fetch_phenom, base_url=base_url, source=company["name"], keywords=keyword,
            )
            for job in jobs or []:
                jobs_by_key[(job["source"], job["external_id"])] = job

    return list(jobs_by_key.values())


def scrape_getnoticed_live(config: dict) -> list[dict]:
    jobs_by_key: dict[tuple[str, str], dict] = {}

    for company in config["companies"]:
        base_url = company.get("getnoticed_base_url")
        if not base_url:
            continue
        for keyword in config["keywords"]:
            jobs = _safe_fetch(
                f"getnoticed:{company['name']}:{keyword}",
                fetch_getnoticed, base_url=base_url, source=company["name"], keywords=keyword,
            )
            for job in jobs or []:
                jobs_by_key[(job["source"], job["external_id"])] = job

    return list(jobs_by_key.values())


def scrape_brassring_live(config: dict) -> list[dict]:
    jobs_by_key: dict[tuple[str, str], dict] = {}

    for company in config["companies"]:
        partner_id = company.get("brassring_partner_id")
        site_id = company.get("brassring_site_id")
        if not partner_id or not site_id:
            continue
        for keyword in config["keywords"]:
            jobs = _safe_fetch(
                f"brassring:{company['name']}:{keyword}",
                fetch_brassring, partner_id=partner_id, site_id=site_id, source=company["name"], keywords=keyword,
            )
            for job in jobs or []:
                jobs_by_key[(job["source"], job["external_id"])] = job

    return list(jobs_by_key.values())


def scrape_deel_live(config: dict) -> list[dict]:
    jobs_by_key: dict[tuple[str, str], dict] = {}

    for company in config["companies"]:
        company_slug = company.get("deel_company_slug")
        if not company_slug:
            continue
        for keyword in config["keywords"]:
            jobs = _safe_fetch(
                f"deel:{company['name']}:{keyword}",
                fetch_deel, company_slug=company_slug, source=company["name"], keywords=keyword,
            )
            for job in jobs or []:
                jobs_by_key[(job["source"], job["external_id"])] = job

    return list(jobs_by_key.values())


def scrape_wba_live(config: dict) -> list[dict]:
    jobs_by_key: dict[tuple[str, str], dict] = {}

    for company in config["companies"]:
        base_url = company.get("wba_base_url")
        if not base_url:
            continue
        for keyword in config["keywords"]:
            jobs = _safe_fetch(
                f"wba:{company['name']}:{keyword}",
                fetch_wba, base_url=base_url, source=company["name"], keywords=keyword,
            )
            for job in jobs or []:
                jobs_by_key[(job["source"], job["external_id"])] = job

    return list(jobs_by_key.values())


def scrape_tsf_live(config: dict) -> list[dict]:
    # TSF doesn't filter by keyword server-side (see tsf_scraper.py) -- every
    # call returns the same full list, so calling it once per company is enough.
    jobs = []

    for company in config["companies"]:
        base_url = company.get("tsf_base_url")
        if not base_url:
            continue
        jobs += _safe_fetch(f"tsf:{company['name']}", fetch_tsf, base_url=base_url, source=company["name"]) or []

    return jobs


def scrape_werkenvoornederland_live(config: dict) -> list[dict]:
    # No relevance-based keyword search (term=employer name finds every job for
    # that employer, not a subset matching our own keywords) -- so just like
    # Greenhouse/UWV: fetch everything per organization, matching/scorer.py
    # filters locally on our keywords.
    jobs = []

    for company in config["companies"]:
        term = company.get("wvn_term")
        if not term:
            continue
        jobs += _safe_fetch(
            f"wvn:{company['name']}",
            fetch_wvn, term=term, source=company["name"], employer_match=company.get("wvn_employer_match"),
        ) or []

    return jobs


def scrape_no_keyword_platforms_live(config: dict) -> list[dict]:
    # Greenhouse, Jobylon, Homerun, Recruitee, UWV, VodafoneZiggo, Ashby and
    # Mollie have no (usable) server-side keyword filter -- each returns the
    # full current job list in one call, so no per-keyword loop is needed
    # (matching/scorer.py filters locally).
    jobs = []

    for company in config["companies"]:
        if company.get("greenhouse_board_token"):
            jobs += _safe_fetch(
                f"greenhouse:{company['name']}",
                fetch_greenhouse, board_token=company["greenhouse_board_token"], source=company["name"],
            ) or []
        if company.get("jobylon_base_url"):
            jobs += _safe_fetch(
                f"jobylon:{company['name']}", fetch_jobylon, base_url=company["jobylon_base_url"], source=company["name"],
            ) or []
        if company.get("homerun_feed_slug"):
            jobs += _safe_fetch(
                f"homerun:{company['name']}", fetch_homerun, feed_slug=company["homerun_feed_slug"], source=company["name"],
            ) or []
        if company.get("recruitee_company_slug"):
            jobs += _safe_fetch(
                f"recruitee:{company['name']}",
                fetch_recruitee, company_slug=company["recruitee_company_slug"], source=company["name"],
            ) or []
        if company.get("ats") == "uwv":
            jobs += _safe_fetch(f"uwv:{company['name']}", fetch_uwv, source=company["name"]) or []
        if company.get("vodafoneziggo_base_url"):
            jobs += _safe_fetch(
                f"vodafoneziggo:{company['name']}",
                fetch_vodafoneziggo, base_url=company["vodafoneziggo_base_url"], source=company["name"],
            ) or []
        if company.get("ashby_board_token"):
            jobs += _safe_fetch(
                f"ashby:{company['name']}",
                fetch_ashby, board_token=company["ashby_board_token"], source=company["name"],
            ) or []
        if company.get("mollie_base_url"):
            jobs += _safe_fetch(
                f"mollie:{company['name']}",
                fetch_mollie, base_url=company["mollie_base_url"], source=company["name"],
            ) or []

    return jobs


def scrape(scrape_live: bool, config: dict) -> list[dict]:
    if scrape_live:
        # Live scraping is only enabled for companies on platforms with a
        # public JSON/HTML search that needs no login/account (Workday, SAP
        # SuccessFactors, Radancy/TalentBrew, Dropr, Google Careers,
        # SmartRecruiters, Oracle Recruiting Cloud, Eightfold, Avature,
        # Phenom, GetNoticed, BrassRing, Deel, Greenhouse, Jobylon, Homerun,
        # Recruitee). Company pages (still
        # synthetic fixtures), LinkedIn and Indeed stay off until those are
        # tested and approved separately (see CLAUDE.md's hard rules).
        return (
            scrape_workday_live(config)
            + scrape_successfactors_live(config)
            + scrape_radancy_live(config)
            + scrape_dropr_live(config)
            + scrape_google_live(config)
            + scrape_smartrecruiters_live(config)
            + scrape_oracle_live(config)
            + scrape_eightfold_live(config)
            + scrape_avature_live(config)
            + scrape_phenom_live(config)
            + scrape_getnoticed_live(config)
            + scrape_brassring_live(config)
            + scrape_deel_live(config)
            + scrape_wba_live(config)
            + scrape_tsf_live(config)
            + scrape_werkenvoornederland_live(config)
            + scrape_no_keyword_platforms_live(config)
        )

    jobs = []
    jobs += parse_company_page((SAMPLE_DIR / "adidas_sample.html").read_text(), "adidas")
    jobs += parse_company_page((SAMPLE_DIR / "nike_sample.html").read_text(), "nike")
    jobs += parse_linkedin((SAMPLE_DIR / "linkedin_sample.html").read_text())
    jobs += parse_indeed((SAMPLE_DIR / "indeed_sample.html").read_text())
    return jobs


def store_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO jobs (source, external_id, title, company, location, url, description, scraped_at) "
        "VALUES (:source, :external_id, :title, :company, :location, :url, :description, CURRENT_TIMESTAMP)",
        jobs,
    )
    conn.commit()


def run(scrape_live: bool, dry_run: bool) -> dict:
    """
    Slow cycle (runs on the 3-hour systemd timer): scrape, score, and send a
    Telegram approval request for every newly-scored job. Doesn't process
    Telegram replies itself and doesn't generate letters -- that happens in
    approval_worker.py, as a separate fast cycle (~90s), so an approval/
    rejection doesn't have to wait for the next scrape run. Also: both cycles
    would otherwise race on the same Telegram offset (app_state).
    """
    conn = get_db()
    config = load_config()

    scraped = scrape(scrape_live, config)
    store_jobs(conn, scraped)

    scored_count = score_jobs(conn, config)

    # Ask for approval (Telegram or dashboard) on every newly-scored job before
    # the expensive steps run -- fetching the job description, the relevance
    # check, and letter generation all cost Claude API calls. In DRY_RUN there's
    # no real cost anyway, so auto-approve right away to keep the whole flow
    # testable end to end.
    requested_ids = []
    for row in conn.execute("SELECT * FROM jobs WHERE status = 'scored'").fetchall():
        job = dict(row)
        if dry_run:
            print("[DRY_RUN] would send an approval request (auto-approved):\n" + build_approval_request_text(job))
            conn.execute("UPDATE jobs SET status = 'approved' WHERE id = ?", (job["id"],))
        else:
            result = send_approval_request(job)
            message_id = result.get("result", {}).get("message_id")
            conn.execute(
                "UPDATE jobs SET status = 'pending_approval', telegram_message_id = ? WHERE id = ?",
                (message_id, job["id"]),
            )
        conn.commit()
        requested_ids.append(job["id"])

    conn.close()
    return {
        "scraped": len(scraped),
        "scored": scored_count,
        "approval_requested": len(requested_ids),
    }


if __name__ == "__main__":
    load_dotenv(ROOT / ".env")  # does nothing if .env doesn't exist yet

    # Decoupled on purpose: SCRAPE_LIVE only controls fetching jobs (Workday
    # etc., public, no credentials needed). DRY_RUN controls the costly/
    # external steps (Claude API for the letter generator, Telegram sends) and
    # requires real credentials in .env once you set it to false.
    scrape_live = os.environ.get("SCRAPE_LIVE", "false").lower() == "true"
    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"

    result = run(scrape_live=scrape_live, dry_run=dry_run)
    print(result)
