import re
import sqlite3
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPANIES_PATH = ROOT / "companies.yaml"
PROFILE_PATH = ROOT / "profile.yaml"

# Some platforms (e.g. Radancy/TalentBrew on multi-location jobs) only return a
# vague indication ("Multiple Locations", "Madrid, ES+10 more") instead of the
# actual list of cities -- the job detail page does have it, but that would
# cost an extra request per job. So we don't know whether Amsterdam is among
# them: no location bonus (can't confirm it), but also explicitly no "outside
# the Netherlands" penalty (that could be unfair).
AMBIGUOUS_LOCATION_RE = re.compile(r"multiple location|\+\s*\d+\s*more")

# "Remote" counts as Amsterdam -- but only for companies explicitly known to be
# 100% remote (companies.yaml: remote_friendly: true, e.g. GitLab). For regular
# companies, "Remote, US" in practice almost always means "remote within the
# US", not worldwide -- so the foreign-location penalty still applies there.
REMOTE_RE = re.compile(r"\bremote\b", re.IGNORECASE)


def _remote_friendly_companies(config: dict) -> set[str]:
    return {c["name"] for c in config.get("companies", []) if c.get("remote_friendly")}


# Two structural patterns that the plain marker lists miss (no "Netherlands"/
# country name anywhere in the string, but a recognizable code is present):
# - Workday/VF Corp region path "EMEA > BEL > Antwerp > ..." -- the middle
#   segment is an ISO-3166 alpha-3 country code.
# - US state code without a standalone "US"/"USA" next to it, e.g. "Boston, MA".
# Both are case-sensitive, so these regexes run on the ORIGINAL (not
# lowercased) location text.
WORKDAY_REGION_CODE_RE = re.compile(r">\s*([A-Z]{3})\s*>")
US_STATE_CODE_RE = re.compile(
    r",\s*(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|"
    r"MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b"
)
# Standalone "US"/"USA" as an uppercase word (e.g. "Hoboken US HQ") -- not as a
# plain lowercase marker string, since that would too easily match by accident.
US_WORD_RE = re.compile(r"\bUSA?\b")


def _is_foreign_location(location_raw: str, location_lower: str, loc_cfg: dict) -> bool:
    is_netherlands = any(m in location_lower for m in loc_cfg.get("netherlands_markers", []))
    is_foreign = any(m in location_lower for m in loc_cfg.get("foreign_markers", []))

    region_codes = WORKDAY_REGION_CODE_RE.findall(location_raw)
    if region_codes:
        if "NLD" in region_codes:
            is_netherlands = True
        if any(c != "NLD" for c in region_codes):
            is_foreign = True

    if US_STATE_CODE_RE.search(location_raw) or US_WORD_RE.search(location_raw):
        is_foreign = True

    return is_foreign and not is_netherlands


def _load_profile_yaml(path: Path) -> dict:
    # profile.yaml is gitignored, so it's the single most common first
    # mistake a new user following the README makes -- a bare
    # FileNotFoundError here gives no hint what to do about it.
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        def _display(p: Path) -> str:
            try:
                return str(p.relative_to(ROOT))
            except ValueError:
                return str(p)

        raise FileNotFoundError(
            f"{path} not found -- copy the template first: "
            f"cp {_display(ROOT / 'profile.example.yaml')} {_display(path)} "
            f"(or run setup_wizard.py)"
        ) from None


def load_config(companies_path: Path = COMPANIES_PATH, profile_path: Path = PROFILE_PATH) -> dict:
    """
    Loads and merges companies.yaml (the shareable ATS/company database) and
    profile.yaml (personal keywords/location/scoring preferences, gitignored)
    into a single dict with the same shape both files used to have together in
    the old config.yaml -- so every caller (scheduler.py, approval_worker.py,
    dashboard/app.py, all scrapers/tests) keeps working unchanged.
    """
    with open(companies_path) as f:
        companies = yaml.safe_load(f)
    profile = _load_profile_yaml(profile_path)

    return {**companies, **profile}


def load_profile(profile_path: Path = PROFILE_PATH) -> dict:
    """Loads just profile.yaml -- used for the `sender` details (name/address/
    email/url) shown on the letterhead of downloaded cover letters."""
    return _load_profile_yaml(profile_path)


def score_breakdown(job: dict, config: dict) -> dict:
    """
    Builds the individual components that score_job() adds up into the final
    score (title_score, location_score, penalty) -- reused by the dashboard
    for the "why this match" card, so the scoring logic only lives in one place.
    """
    title = (job.get("title") or "").lower()
    location_raw = job.get("location") or ""
    location = location_raw.lower()

    exclude_terms = config.get("scoring", {}).get("exclude_title_keywords", [])
    if any(re.search(rf"\b{re.escape(term.lower())}\b", title) for term in exclude_terms):
        return {"excluded": True, "title_score": 0.0, "location_score": 0.0, "penalty": 0.0, "total": -1.0}

    # Word-boundary matching (\b...\b) instead of a plain substring: needed
    # since "ai" is a keyword -- a substring check would otherwise also count
    # as a match inside words like "Retail" or "Chair".
    weights = config.get("keyword_weights", {})
    weight_sum = sum(
        weights.get(kw.lower(), 1.0)
        for kw in config["keywords"]
        if re.search(rf"\b{re.escape(kw.lower())}\b", title)
    )
    title_score = min(weight_sum / 2, 1.0)

    is_remote_ok = (
        REMOTE_RE.search(location_raw) is not None
        and job.get("source") in _remote_friendly_companies(config)
    )

    loc_cfg = config["location"]
    bonus_cities = loc_cfg.get("bonus_cities") or [loc_cfg["center"]]
    location_score = 1.0 if is_remote_ok or any(c.lower() in location for c in bonus_cities) else 0.0

    penalty = 0.0
    if not is_remote_ok and location and not AMBIGUOUS_LOCATION_RE.search(location):
        if _is_foreign_location(location_raw, location, loc_cfg):
            penalty = loc_cfg.get("outside_netherlands_penalty", 0.0)

    total = round(0.7 * title_score + 0.3 * location_score + penalty, 3)
    return {
        "excluded": False,
        "title_score": title_score,
        "location_score": location_score,
        "penalty": penalty,
        "total": total,
    }


def score_job(job: dict, config: dict) -> float:
    return score_breakdown(job, config)["total"]


def score_jobs(conn: sqlite3.Connection, config: dict) -> int:
    """Scores every job with status 'new'. Sets status to 'scored' (>= threshold,
    goes on to letter generation) or 'rejected' (below threshold). Returns the
    number of jobs that clear the threshold."""
    threshold = config["scoring"]["threshold"]
    rows = conn.execute("SELECT id, title, location, source FROM jobs WHERE status = 'new'").fetchall()

    scored_count = 0
    for job_id, title, location, source in rows:
        score = score_job({"title": title, "location": location, "source": source}, config)
        if score >= threshold:
            conn.execute(
                "UPDATE jobs SET relevance_score = ?, status = 'scored' WHERE id = ?",
                (score, job_id),
            )
            scored_count += 1
        else:
            conn.execute(
                "UPDATE jobs SET relevance_score = ?, status = 'rejected', "
                "rejected_at = CURRENT_TIMESTAMP, rejected_stage = 'scoring', "
                "rejected_reason = ? WHERE id = ?",
                (score, f"score {score} below threshold {threshold}", job_id),
            )

    conn.commit()
    return scored_count
