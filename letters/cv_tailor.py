"""
Generates a per-job-posting tailored variant of the short CV (letters/
cv_short.yaml / cv_short_nl.yaml): reorders/rewords the existing experience
bullets and skills-table entries to mirror the vacature's own terminology,
and flags vacature terms the CV doesn't address. Mirrors letters/generator.py
and letters/interview_prep.py's shape (style guide, build_prompt, generate_*,
save_*) but kept as its own module for the same reason interview_prep.py is:
content, audience and constraints differ from the cover letter.

Deliberately narrow in scope: only `experience[].bullets` and
`skills_table[].text` are ever rewritten -- never `projects` (cv_short.yaml's
project entries use their own hand-written tech/description style that
doesn't have an automatic source to select from), never dates/titles/
companies/skill labels. The merge in `_merge_variant` only accepts a field
if it passes validation against the source structure; anything invalid or
missing falls back to the untouched original for that field, so a malformed
or partial LLM response can never corrupt the CV, only under-tailor it.
"""

import copy
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from matching.scorer import load_profile

SENDER_NAME = load_profile()["sender"]["name"]

LANGUAGE_NAMES = {"nl": "Dutch", "en": "English"}

CV_TAILOR_STYLE_GUIDE = """\
- Never invent, add, or remove a factual claim (employer, dates, skill,
  achievement, metric) that isn't already present in the source CV data below.
  You are reordering and lightly rewording existing content, not writing new
  content.
- For each experience entry, you may reorder its bullets (most relevant to
  this vacature first) and lightly reword a bullet's phrasing to mirror the
  vacature's own terminology -- only when it is a genuine synonym for
  something the bullet already describes (e.g. "stakeholder management" ->
  "cross-functional alignment" is fine if that's what the bullet already
  describes; inventing a new claim is not).
- For skills_table, you may reorder the rows and lightly reword each row's
  `text` value the same way -- same content, vacature-mirrored terminology,
  same '·'-separated format.
- When a term could go either way, prefer whichever phrasing is the more
  standard, widely-recognized industry term over a more original or
  idiosyncratic one -- several major ATS platforms (Workday, Phenom) match
  against a normalized skills taxonomy rather than raw text, so a
  recognizable standard term carries further than clever phrasing.
- Do not touch titles, companies, dates, or skills_table labels.
- Also list, in `missing_terms`, up to 5 short terms/phrases from the
  vacature text that are genuinely not reflected anywhere in the CV data --
  for {sender_name} to consider adding by hand, never for you to add yourself.
- Write any reworded text in {language_name}, matching the job posting's
  language."""


def build_cv_tailor_prompt(job: dict, cv_data: dict, language: str = "en") -> tuple[str, str]:
    style_guide = CV_TAILOR_STYLE_GUIDE.format(
        language_name=LANGUAGE_NAMES.get(language, "English"), sender_name=SENDER_NAME
    )
    system_prompt = (
        f"You are tailoring {SENDER_NAME}'s CV for a specific job posting.\n\nRules:\n{style_guide}\n\n"
        "Respond with ONLY a JSON object, no other text, no markdown code fences, shaped exactly like:\n"
        '{"experience": [{"title": "<exact title from source>", "bullets": ["...", "..."]}], '
        '"skills_table": [{"label": "<exact label from source>", "text": "..."}], '
        '"missing_terms": ["...", "..."]}'
    )

    source = {
        "experience": [{"title": e["title"], "bullets": e["bullets"]} for e in cv_data["experience"]],
        "skills_table": [{"label": r["label"], "text": r["text"]} for r in cv_data["skills_table"]],
    }
    user_prompt = (
        f"Job: {job.get('title')} at {job.get('company')}\n"
        f"Job description:\n{job.get('description', '')}\n\n"
        f"Source CV data (JSON):\n{json.dumps(source, ensure_ascii=False, indent=2)}\n\n"
        "Return the tailored JSON object."
    )
    return system_prompt, user_prompt


def _merge_variant(cv_data: dict, llm_result: dict) -> dict:
    merged = copy.deepcopy(cv_data)

    by_title = {e["title"]: e for e in llm_result.get("experience", []) if isinstance(e, dict)}
    for entry in merged["experience"]:
        candidate = by_title.get(entry["title"])
        if not candidate:
            continue
        bullets = candidate.get("bullets")
        if isinstance(bullets, list) and bullets and all(isinstance(b, str) and b.strip() for b in bullets):
            entry["bullets"] = bullets

    candidate_skills = llm_result.get("skills_table")
    if isinstance(candidate_skills, list):
        source_labels = {r["label"] for r in merged["skills_table"]}
        candidate_by_label = {
            r.get("label"): r.get("text")
            for r in candidate_skills
            if isinstance(r, dict) and isinstance(r.get("text"), str) and r.get("text", "").strip()
        }
        # Only accept the reorder/reword if every source label is present and
        # nothing extra was invented -- otherwise a row could silently vanish
        # from the rendered CV, which is worse than just skipping the reword.
        if source_labels == set(candidate_by_label):
            merged["skills_table"] = [
                {"label": r["label"], "text": candidate_by_label[r["label"]]} for r in merged["skills_table"]
            ]

    return merged


def generate_cv_variant(
    job: dict, cv_data: dict, language: str, dry_run: bool
) -> tuple[dict, list[str]]:
    if dry_run:
        return copy.deepcopy(cv_data), ["[DRY_RUN mock -- no real API call made]"]

    system_prompt, user_prompt = build_cv_tailor_prompt(job, cv_data, language)

    from anthropic import Anthropic

    client = Anthropic()
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = "\n".join(block.text for block in response.content if block.type == "text").strip()

    try:
        # The prompt asks for a bare JSON object, but models occasionally wrap
        # it in a markdown fence anyway -- strip that before parsing rather
        # than failing on it.
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw[raw.index("\n") + 1 :] if "\n" in raw else raw
        llm_result = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Never let a malformed LLM response break the approval cycle -- fall
        # back to the untouched CV, same spirit as scheduler.py's _safe_fetch.
        return copy.deepcopy(cv_data), []

    merged = _merge_variant(cv_data, llm_result)
    missing_terms = llm_result.get("missing_terms")
    missing_terms = [t for t in missing_terms if isinstance(t, str) and t.strip()] if isinstance(missing_terms, list) else []
    return merged, missing_terms


def save_cv_variant(conn: sqlite3.Connection, job_id: int, data: dict, missing_terms: list[str], language: str) -> None:
    conn.execute(
        "INSERT INTO cv_variants (job_id, language, data, missing_terms, generated_at) VALUES (?, ?, ?, ?, ?)",
        (
            job_id,
            language,
            json.dumps(data, ensure_ascii=False),
            json.dumps(missing_terms, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
