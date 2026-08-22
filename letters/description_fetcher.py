import re

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
MAX_CHARS = 6000


def _html_to_text(html: str) -> str:
    text = BeautifulSoup(html or "", "lxml").get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:MAX_CHARS]


def fetch_workday_description(job: dict, company: dict) -> str | None:
    host = company["workday_host"]
    site = company["workday_site"]
    tenant = host.split(".")[0]
    url = job.get("url", "")
    # Search on "/{site}" instead of a fixed "https://{host}/en-US/{site}" prefix
    # -- older database rows still have the /en-US/ form, newer ones don't (see
    # scrapers/workday_scraper.py); this keeps working with both.
    marker = f"/{site}"
    if not url.startswith(f"https://{host}") or marker not in url:
        return None
    external_path = url.split(marker, 1)[1]

    resp = requests.get(
        f"https://{host}/wday/cxs/{tenant}/{site}{external_path}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    desc_html = resp.json().get("jobPostingInfo", {}).get("jobDescription")
    return _html_to_text(desc_html) if desc_html else None


def fetch_oracle_description(job: dict, company: dict) -> str | None:
    resp = requests.get(
        f"https://{company['oracle_host']}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails",
        params={
            "onlyData": "true",
            "expand": "all",
            "finder": f'ById;Id="{job["external_id"]}",siteNumber={company["oracle_site_number"]}',
        },
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    items = resp.json().get("items") or []
    if not items:
        return None

    item = items[0]
    parts = [
        item.get(k)
        for k in ("ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr")
    ]
    combined = "\n\n".join(p for p in parts if p)
    return _html_to_text(combined) if combined else None


def fetch_smartrecruiters_description(job: dict, company: dict) -> str | None:
    resp = requests.get(
        f"https://api.smartrecruiters.com/v1/companies/{company['smartrecruiters_company_id']}"
        f"/postings/{job['external_id']}",
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    sections = resp.json().get("jobAd", {}).get("sections", {})
    parts = [sections.get(k, {}).get("text") for k in ("jobDescription", "qualifications", "additionalInformation")]
    combined = "\n\n".join(p for p in parts if p)
    return _html_to_text(combined) if combined else None


def fetch_greenhouse_description(job: dict, company: dict) -> str | None:
    resp = requests.get(
        f"https://boards-api.greenhouse.io/v1/boards/{company['greenhouse_board_token']}"
        f"/jobs/{job['external_id']}",
        params={"content": "true"},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    content = resp.json().get("content")
    return _html_to_text(content) if content else None


def fetch_phenom_description(job: dict, company: dict) -> str | None:
    parsed_host = re.match(r"https?://([^/]+)", company["phenom_base_url"])
    if not parsed_host:
        return None

    resp = requests.post(
        f"https://{parsed_host.group(1)}/widgets",
        json={
            "ddoKey": "jobDetail",
            "lang": "en_us",
            "deviceType": "desktop",
            "pageName": "job-detail",
            "jobId": job["external_id"],
        },
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    desc_html = resp.json().get("jobDetail", {}).get("data", {}).get("job", {}).get("description")
    return _html_to_text(desc_html) if desc_html else None


def fetch_generic_description(job: dict, company: dict | None = None) -> str | None:
    """
    Fallback for platforms without their own JSON detail endpoint that we
    already know about (Radancy, SF old template, Avature old template,
    GetNoticed, Jobylon, Homerun, BrassRing, Recruitee, Deel, Eightfold, custom
    sites): fetch the job URL and strip the HTML down to readable text. Works
    well for server-side rendered detail pages, less well for client-side
    SPAs -- no per-site investigation has been done for this, it's
    deliberately a best-effort fallback.
    """
    if not job.get("url"):
        return None

    resp = requests.get(job["url"], headers={"User-Agent": USER_AGENT}, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "svg"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:MAX_CHARS] if text else None


FETCHERS_BY_ATS = {
    "workday": fetch_workday_description,
    "oracle_recruiting_cloud": fetch_oracle_description,
    "smartrecruiters": fetch_smartrecruiters_description,
    "greenhouse": fetch_greenhouse_description,
    "phenom": fetch_phenom_description,
}


def fetch_description(job: dict, config: dict) -> str | None:
    """
    Fetches the full job description for one job -- meant to only be called
    for the small subset of jobs already above the score threshold, not for
    every scraped job (that would multiply the number of requests by a factor
    of hundreds, for text we throw away in most cases anyway).
    """
    if job.get("description"):
        # Some platforms (e.g. Ashby) already supply the full job description
        # at scrape time -- a separate fetch is then unnecessary.
        return job["description"]

    company = next((c for c in config["companies"] if c["name"] == job.get("company")), None)
    ats = company.get("ats") if company else None
    fetcher = FETCHERS_BY_ATS.get(ats, fetch_generic_description)

    try:
        return fetcher(job, company or {})
    except Exception as e:
        print(f"[description_fetcher] couldn't fetch the job description for {job.get('title')!r}: {e}")
        return None
