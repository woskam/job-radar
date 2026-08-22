import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from matching.scorer import load_profile

PROJECTS_PATH = ROOT / "letters" / "projects.json"
CV_PATH_EN = ROOT / "letters" / "cv.txt"
CV_PATH_NL = ROOT / "letters" / "cv_nl.txt"
EXAMPLE_LETTER_PATH = ROOT / "letters" / "example_cover_letter.txt"

SENDER_NAME = load_profile()["sender"]["name"]

LANGUAGE_NAMES = {"nl": "Dutch", "en": "English"}

STYLE_GUIDE_TEMPLATE = """\
- Write the whole letter in {language_name}, the same language as the job posting.
- No fluff, no em-dashes, direct and to the point.
- Slightly less "perfect" language is fine -- it should sound like {sender_name}, not like AI output.
- Open with a claim for why he's the right candidate, followed by evidence from the projects.
- Use 2-3 of the supplied projects, not all of them -- pick the ones that best match
  the job posting, not the same ones by default."""

# Simple, dependency-free language detection instead of a library or an extra
# Claude call -- job postings are almost always NL or EN, so a word list of
# common, unambiguous function words per language is enough.
DUTCH_MARKERS = {
    "de", "het", "een", "van", "voor", "met", "wij", "je", "jij", "uw", "bij", "en",
    "worden", "wordt", "zoeken", "zoekt", "ervaring", "kandidaat", "vacature", "functie",
    "medewerker", "werkzaamheden", "sollicitatie", "opleiding", "salaris", "dienstverband",
    "werkgever", "organisatie", "team", "collega's", "kennis", "vaardigheden",
}
ENGLISH_MARKERS = {
    "the", "and", "for", "with", "we", "you", "your", "is", "are", "looking", "candidate",
    "position", "role", "experience", "responsibilities", "requirements", "qualifications",
    "salary", "employer", "company", "will", "have", "our", "this", "team", "join",
}


def detect_language(text: str) -> str:
    words = re.findall(r"[a-zà-ÿ']+", (text or "").lower())
    nl_hits = sum(1 for w in words if w in DUTCH_MARKERS)
    en_hits = sum(1 for w in words if w in ENGLISH_MARKERS)
    return "nl" if nl_hits > en_hits else "en"


def load_projects(path: Path = PROJECTS_PATH) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def load_cv(language: str = "en") -> str:
    path = CV_PATH_NL if language == "nl" else CV_PATH_EN
    if not path.exists() and path == CV_PATH_NL:
        # cv_nl.txt is optional -- fall back to the English CV if you haven't
        # written a separate Dutch one yet.
        path = CV_PATH_EN
    return path.read_text()


def load_example_letter(path: Path = EXAMPLE_LETTER_PATH) -> str:
    return path.read_text()


def select_relevant_projects(job: dict, projects: list[dict], n: int = 3) -> list[dict]:
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()

    def hits(project: dict) -> int:
        return sum(1 for tag in project.get("tags", []) if tag.lower() in text)

    ranked = sorted(projects, key=hits, reverse=True)
    return ranked[:n]


def build_prompt(
    job: dict, cv_text: str, selected_projects: list[dict], example_letter: str = "", language: str = "en"
) -> tuple[str, str]:
    style_guide = STYLE_GUIDE_TEMPLATE.format(
        language_name=LANGUAGE_NAMES.get(language, "English"), sender_name=SENDER_NAME
    )
    system_prompt = f"You are writing a cover letter draft on behalf of {SENDER_NAME}.\n\nStyle rules:\n{style_guide}"
    if example_letter:
        system_prompt += (
            f"\n\nExample of a letter {SENDER_NAME} wrote earlier (match the same tone/style, "
            "don't copy it verbatim):\n\n" + example_letter
        )

    def format_project(p: dict) -> str:
        lines = [f"- {p['name']}: {p['one_liner']} (role: {p['role']}, outcome: {p['outcome']})"]
        for h in p.get("highlights", []):
            lines.append(f"    - {h}")
        return "\n".join(lines)

    projects_text = "\n\n".join(format_project(p) for p in selected_projects)

    user_prompt = (
        f"CV:\n{cv_text}\n\n"
        f"Job: {job.get('title')} at {job.get('company')}\n"
        f"Job description:\n{job.get('description', '')}\n\n"
        f"Relevant projects to use as evidence:\n{projects_text}\n\n"
        "Write the cover letter draft."
    )
    return system_prompt, user_prompt


def generate_letter(
    job: dict, cv_text: str, projects: list[dict], dry_run: bool, language: str = "en"
) -> str:
    selected = select_relevant_projects(job, projects)
    example_letter = load_example_letter() if EXAMPLE_LETTER_PATH.exists() else ""
    system_prompt, user_prompt = build_prompt(job, cv_text, selected, example_letter, language)

    if dry_run:
        project_lines = "\n".join(f"- {p['name']}: {p['outcome']}" for p in selected)
        return (
            f"[DRY_RUN mock draft -- no real API call made]\n\n"
            f"Application for {job.get('title')} at {job.get('company')}.\n\n"
            f"Projects used as evidence:\n{project_lines}\n"
        )

    from anthropic import Anthropic

    client = Anthropic()
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=3000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text_blocks = [block.text for block in response.content if block.type == "text"]
    return "\n".join(text_blocks)


def save_letter(conn: sqlite3.Connection, job_id: int, draft: str, language: str = "en") -> None:
    conn.execute(
        "INSERT INTO letters (job_id, draft, generated_at, language) VALUES (?, ?, ?, ?)",
        (job_id, draft, datetime.now(timezone.utc).isoformat(), language),
    )
    conn.execute("UPDATE jobs SET status = 'letter_drafted' WHERE id = ?", (job_id,))
    conn.commit()


if __name__ == "__main__":
    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"

    mock_job = {
        "title": "Director Digital Sales Benelux",
        "company": "Mock Retail Group",
        "description": "We are looking for a Director Digital Sales with experience in ecommerce and wholesale.",
    }

    projects = load_projects()
    language = detect_language(mock_job["description"])
    print(f"detected language: {language}")
    draft = generate_letter(mock_job, cv_text="[mock cv]", projects=projects, dry_run=dry_run, language=language)
    print(draft)
