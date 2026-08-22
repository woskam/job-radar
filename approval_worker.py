import os

from dotenv import load_dotenv

from letters.description_fetcher import fetch_description
from letters.generator import detect_language, generate_letter, load_cv, load_projects, save_letter
from matching.scorer import load_config
from matching.telegram_approval import process_telegram_approvals
from notify.telegram_bot import send_letter
from scheduler import ROOT, get_db


def run_approvals(dry_run: bool) -> dict:
    """
    Fast cycle (runs on the ~90s systemd timer): processes Telegram
    Approve/Reject clicks and rejection reasons, and immediately generates the
    cover-letter draft for every newly-approved job (via Telegram or the
    dashboard), sent over Telegram. Decoupled from scheduler.py's slow
    scrape/score cycle so a reply doesn't have to wait up to 3 hours for the
    next run.
    """
    conn = get_db()
    config = load_config()

    processed = 0
    if not dry_run:
        processed = process_telegram_approvals(conn)

    projects = load_projects()

    drafted_ids = []
    for row in conn.execute("SELECT * FROM jobs WHERE status = 'approved'").fetchall():
        job = dict(row)

        # Only fetch the job description for jobs that have already been
        # approved (see letters/description_fetcher.py) -- not for every
        # scraped job.
        description = fetch_description(job, config)
        if description:
            job["description"] = description
            conn.execute("UPDATE jobs SET description = ? WHERE id = ?", (description, job["id"]))
            conn.commit()

        # The letter's (and the CV's) language follows the job posting's language.
        language = detect_language(job.get("description") or job.get("title") or "")
        cv_text = load_cv(language)

        # No automatic content-relevance check anymore after approval -- your
        # "Yes" in Telegram/the dashboard is the relevance check. That step used
        # to silently overrule an explicit approval without telling you.
        draft = generate_letter(job, cv_text=cv_text, projects=projects, dry_run=dry_run, language=language)
        save_letter(conn, job["id"], draft, language=language)
        drafted_ids.append(job["id"])

        if dry_run:
            print(f"[DRY_RUN] would send the letter over Telegram for {job['title']} at {job['company']}:\n{draft}")
        else:
            send_letter(job, draft)

    conn.close()
    return {
        "telegram_updates_processed": processed,
        "drafted": len(drafted_ids),
    }


if __name__ == "__main__":
    load_dotenv(ROOT / ".env")

    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"

    result = run_approvals(dry_run=dry_run)
    print(result)
