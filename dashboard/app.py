import io
import os
import re
import sqlite3
import sys
from pathlib import Path

from flask import Flask, redirect, render_template, request, send_file, url_for

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db.migrations import ensure_columns
from letters.cv_builder import build_cv_docx, build_cv_pdf
from letters.cv_short_builder import CV_SHORT_PATH_NL, build_short_cv_docx, build_short_cv_pdf
from letters.document_style import DEFAULT_FONT, FONT_OPTIONS, SENDER
from letters.generator import CV_PATH_NL, detect_language
from matching.scorer import load_config, score_breakdown

DB_PATH = Path(os.environ.get("JOB_RADAR_DB_PATH", ROOT / "db" / "job_radar.db"))

app = Flask(__name__)

# Status pill colors, from the design handoff -- extended with 'approved' and
# 'sent', which weren't in the original handoff but do exist here, following
# the same oklch(0.95 .. )/oklch(0.45 ..) formula.
STATUS_META = {
    "pending_approval": {"label": "Needs review", "bg": "#F4F1EA", "fg": "#6E6A63"},
    "approved": {"label": "Writing letter", "bg": "#F4F1EA", "fg": "#6E6A63"},
    "letter_drafted": {"label": "Letter ready", "bg": "oklch(0.95 0.035 95)", "fg": "oklch(0.45 0.08 80)"},
    "reviewed": {"label": "Reviewed", "bg": "oklch(0.95 0.03 215)", "fg": "oklch(0.45 0.09 215)"},
    "sent": {"label": "Sent", "bg": "oklch(0.95 0.05 145)", "fg": "oklch(0.45 0.1 145)"},
    "rejected": {"label": "Rejected", "bg": "#FAF3F2", "fg": "#8A5A55"},
}
DEFAULT_STATUS_META = {"label": "Unknown", "bg": "#F4F1EA", "fg": "#6E6A63"}


def _font_choice() -> dict:
    return FONT_OPTIONS.get(request.args.get("font", DEFAULT_FONT), FONT_OPTIONS[DEFAULT_FONT])


def _letter_filename(job: dict, extension: str) -> str:
    raw = f"cover_letter_{job['company']}_{job['title']}"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("_")[:120]
    return f"{safe}.{extension}"


def status_meta(status: str) -> dict:
    return STATUS_META.get(status, DEFAULT_STATUS_META)


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_columns(conn)
    return conn


def _sidebar_counts(conn: sqlite3.Connection) -> dict:
    return {
        "total": conn.execute("SELECT COUNT(*) FROM jobs WHERE status != 'new'").fetchone()[0],
        "letter_drafted": conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'letter_drafted'").fetchone()[0],
        "sent": conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'sent'").fetchone()[0],
        "rejected": conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'rejected'").fetchone()[0],
    }


PAGE_SIZE = 50
SCORE_OPTIONS = ["0.5", "0.6", "0.65", "0.7", "0.75", "0.8", "0.9", "1.0"]
STRONG_MATCH_THRESHOLD = 0.80


@app.route("/")
def index():
    title = request.args.get("title", "").strip()
    company = request.args.get("company", "").strip()
    location = request.args.get("location", "").strip()
    status = request.args.get("status", "").strip()
    min_score = request.args.get("min_score", "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    where = ["status != 'new'"]
    params: list = []

    if title:
        where.append("title LIKE ?")
        params.append(f"%{title}%")
    if company:
        where.append("company = ?")
        params.append(company)
    if location:
        where.append("location LIKE ?")
        params.append(f"%{location}%")
    if status:
        where.append("status = ?")
        params.append(status)
    if min_score:
        try:
            where.append("relevance_score >= ?")
            params.append(float(min_score))
        except ValueError:
            pass

    where_sql = " AND ".join(where)

    conn = get_db()
    total = conn.execute(f"SELECT COUNT(*) FROM jobs WHERE {where_sql}", params).fetchone()[0]
    total_pages = max(1, -(-total // PAGE_SIZE))  # ceil division
    page = min(page, total_pages)
    offset = (page - 1) * PAGE_SIZE

    jobs = conn.execute(
        f"SELECT * FROM jobs WHERE {where_sql} ORDER BY relevance_score DESC LIMIT ? OFFSET ?",
        params + [PAGE_SIZE, offset],
    ).fetchall()

    statuses = [
        r["status"] for r in conn.execute(
            "SELECT DISTINCT status FROM jobs WHERE status != 'new' ORDER BY status"
        ).fetchall()
    ]
    companies = [
        r["company"] for r in conn.execute(
            "SELECT DISTINCT company FROM jobs WHERE status != 'new' AND company IS NOT NULL ORDER BY company"
        ).fetchall()
    ]
    locations = [
        r["location"] for r in conn.execute(
            "SELECT DISTINCT location FROM jobs WHERE status != 'new' AND location IS NOT NULL ORDER BY location"
        ).fetchall()
    ]
    kpis = {
        "strong_matches": conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE relevance_score >= ?", (STRONG_MATCH_THRESHOLD,)
        ).fetchone()[0],
        "pending_approval": conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'pending_approval'"
        ).fetchone()[0],
        "letter_drafted": conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'letter_drafted'"
        ).fetchone()[0],
        "new_today": conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE date(scraped_at) = date('now')"
        ).fetchone()[0],
    }
    sidebar_counts = _sidebar_counts(conn)
    conn.close()

    filters = {
        "title": title,
        "company": company,
        "location": location,
        "status": status,
        "min_score": min_score,
    }
    return render_template(
        "index.html",
        jobs=jobs,
        statuses=statuses,
        companies=companies,
        locations=locations,
        score_options=SCORE_OPTIONS,
        filters=filters,
        page=page,
        total_pages=total_pages,
        total=total,
        kpis=kpis,
        sidebar_counts=sidebar_counts,
        status_meta=status_meta,
        strong_match_threshold=STRONG_MATCH_THRESHOLD,
    )


def _match_strength(value: float) -> str:
    if value >= 0.7:
        return "strong"
    if value >= 0.3:
        return "average"
    return "weak"


def _match_reasons(job: dict) -> list[dict]:
    # No made-up criteria -- only the components matching/scorer.py actually
    # uses to compute the score.
    breakdown = score_breakdown(job, load_config())
    if breakdown["excluded"]:
        return [{"label": "Title contains an exclusion word", "value": "weak"}]
    location_strength = (
        "strong" if breakdown["location_score"] >= 1.0 else ("weak" if breakdown["penalty"] < 0 else "average")
    )
    return [
        {"label": "Title/role match", "value": _match_strength(breakdown["title_score"])},
        {"label": "Location", "value": location_strength},
    ]


def _timeline(job: dict, letter: sqlite3.Row | None) -> list[dict]:
    if job["status"] == "rejected":
        human_reviewed = job["rejected_stage"] in ("approval", "review")
        step1 = {
            "label": "Reviewed",
            "reached": human_reviewed,
            "submeta": (letter["generated_at"] if letter else None) or ("not yet" if not human_reviewed else "-"),
        }
        step2 = {
            "label": "Rejected",
            "reached": True,
            "submeta": job["rejected_reason"] or "no reason given",
            "danger": True,
        }
    else:
        step1_reached = job["status"] in ("letter_drafted", "reviewed", "sent")
        step1 = {
            "label": "Reviewed",
            "reached": step1_reached,
            "submeta": (letter["generated_at"] if letter else None) or ("not yet" if not step1_reached else "-"),
        }
        step2 = {
            "label": "Sent",
            "reached": job["status"] == "sent",
            "submeta": job["sent_at"] or "not yet",
            "danger": False,
        }
    return [step1, step2]


@app.route("/job/<int:job_id>")
def job_detail(job_id):
    conn = get_db()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    letter = conn.execute(
        "SELECT * FROM letters WHERE job_id = ? ORDER BY id DESC LIMIT 1", (job_id,)
    ).fetchone()
    sidebar_counts = _sidebar_counts(conn)
    conn.close()
    return render_template(
        "job_detail.html",
        job=job,
        letter=letter,
        saved=request.args.get("saved"),
        status_meta=status_meta,
        sidebar_counts=sidebar_counts,
        match_reasons=_match_reasons(dict(job)),
        timeline=_timeline(job, letter),
        font_options=FONT_OPTIONS,
        selected_font=request.args.get("font", DEFAULT_FONT),
    )


@app.route("/job/<int:job_id>/save", methods=["POST"])
def save_draft(job_id):
    final_text = request.form["final_text"]
    conn = get_db()
    letter = conn.execute(
        "SELECT id FROM letters WHERE job_id = ? ORDER BY id DESC LIMIT 1", (job_id,)
    ).fetchone()
    if letter:
        conn.execute(
            "UPDATE letters SET final_text = ?, edited = 1 WHERE id = ?",
            (final_text, letter["id"]),
        )
    else:
        # Can happen if a job was approved via the dashboard but the letter
        # generator (approval_worker.py) hasn't run yet -- without this, a
        # manually typed letter here would silently be lost.
        conn.execute(
            "INSERT INTO letters (job_id, draft, final_text, generated_at, edited) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP, 1)",
            (job_id, final_text, final_text),
        )
    conn.execute("UPDATE jobs SET status = 'reviewed' WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("job_detail", job_id=job_id, saved=1))


@app.route("/job/<int:job_id>/download.docx")
def download_docx(job_id):
    conn = get_db()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    letter = conn.execute(
        "SELECT * FROM letters WHERE job_id = ? ORDER BY id DESC LIMIT 1", (job_id,)
    ).fetchone()
    conn.close()
    if not letter:
        return "no draft letter for this job", 404

    from docx import Document

    from letters.document_style import build_docx_footer, build_docx_header, docx_add_bullet, render_text_blocks

    font = _font_choice()
    language = letter["language"] or detect_language(letter["final_text"] or letter["draft"] or "")
    subject = f"Re: {job['title']} ({job['company']})"
    # Textarea edits from the dashboard submit with \r\n line endings, which
    # wouldn't match the "\n\n" paragraph-break/bullet-line checks below --
    # normalize before splitting, not just for freshly AI-drafted text.
    text = (letter["final_text"] or letter["draft"] or "").replace("\r\n", "\n").replace("\r", "\n")

    doc = Document()
    doc.styles["Normal"].font.name = font["docx"]
    build_docx_header(doc.sections[0], language, subject, font["docx"])
    build_docx_footer(doc.sections[0], font["docx"])
    render_text_blocks(
        text,
        add_paragraph=lambda t: doc.add_paragraph(t),
        add_bullet=lambda t: docx_add_bullet(doc, t, font["docx"]),
    )

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=_letter_filename(dict(job), "docx"),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.route("/job/<int:job_id>/download.pdf")
def download_pdf(job_id):
    conn = get_db()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    letter = conn.execute(
        "SELECT * FROM letters WHERE job_id = ? ORDER BY id DESC LIMIT 1", (job_id,)
    ).fetchone()
    conn.close()
    if not letter:
        return "no draft letter for this job", 404

    from fpdf.enums import XPos, YPos

    from letters.document_style import make_letterhead_pdf, pdf_add_bullet, render_text_blocks

    font = _font_choice()
    language = letter["language"] or detect_language(letter["final_text"] or letter["draft"] or "")
    # Textarea edits from the dashboard submit with \r\n line endings, which
    # wouldn't match the "\n\n" paragraph-break/bullet-line checks below --
    # normalize before splitting, not just for freshly AI-drafted text.
    text = (letter["final_text"] or letter["draft"] or "").replace("\r\n", "\n").replace("\r", "\n")
    # Core PDF fonts only support cp1252 -- replace characters that don't fit
    # (e.g. a single non-Latin name) instead of crashing on one stray character.
    safe_text = text.encode("cp1252", "replace").decode("cp1252")
    subject = f"Re: {job['title']} ({job['company']})".encode("cp1252", "replace").decode("cp1252")

    pdf = make_letterhead_pdf(font["pdf"], language, subject)
    pdf.add_page()

    def add_paragraph(t: str) -> None:
        pdf.set_font(font["pdf"], size=11)
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 6, t, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)

    def add_bullet(t: str) -> None:
        pdf.set_text_color(0, 0, 0)
        pdf_add_bullet(pdf, t, font["pdf"], size=11, line_height=6)
        pdf.ln(2)

    render_text_blocks(safe_text, add_paragraph, add_bullet)

    buf = io.BytesIO(bytes(pdf.output()))
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=_letter_filename(dict(job), "pdf"),
        mimetype="application/pdf",
    )


@app.route("/job/<int:job_id>/status", methods=["POST"])
def update_status(job_id):
    # Only updates the status in the database. Doesn't send/post anything --
    # actually sending the application is done by you, outside this dashboard.
    new_status = request.form["status"]
    if new_status not in ("sent", "rejected", "approved"):
        return "invalid status", 400
    conn = get_db()
    if new_status == "rejected":
        current = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        stage = "approval" if current and current["status"] == "pending_approval" else "review"
        reason = request.form.get("reason", "").strip() or "Rejected via dashboard"
        conn.execute(
            "UPDATE jobs SET status = ?, rejected_at = CURRENT_TIMESTAMP, "
            "rejected_stage = ?, rejected_reason = ? WHERE id = ?",
            (new_status, stage, reason, job_id),
        )
    elif new_status == "sent":
        conn.execute("UPDATE jobs SET status = ?, sent_at = CURRENT_TIMESTAMP WHERE id = ?", (new_status, job_id))
    else:
        conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (new_status, job_id))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


def _cv_filename(extension: str, variant: str) -> str:
    name = SENDER["name"].replace(" ", "_")
    suffix = "_short" if variant == "short" else ""
    return f"CV_{name}{suffix}.{extension}"


@app.route("/cv")
def cv():
    conn = get_db()
    sidebar_counts = _sidebar_counts(conn)
    conn.close()
    variant = request.args.get("variant", "long")
    has_dutch_cv = CV_SHORT_PATH_NL.exists() if variant == "short" else CV_PATH_NL.exists()
    return render_template(
        "cv.html",
        font_options=FONT_OPTIONS,
        selected_font=request.args.get("font", DEFAULT_FONT),
        selected_lang=request.args.get("lang", "en"),
        selected_variant=variant,
        has_dutch_cv=has_dutch_cv,
        sidebar_counts=sidebar_counts,
    )


@app.route("/cv/download.docx")
def cv_download_docx():
    font = _font_choice()
    language = request.args.get("lang", "en")
    variant = request.args.get("variant", "long")

    doc = (
        build_short_cv_docx(language=language, font_name=font["docx"])
        if variant == "short"
        else build_cv_docx(language=language, font_name=font["docx"])
    )
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=_cv_filename("docx", variant),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.route("/cv/download.pdf")
def cv_download_pdf():
    font = _font_choice()
    language = request.args.get("lang", "en")
    variant = request.args.get("variant", "long")

    pdf = (
        build_short_cv_pdf(language=language, font_family=font["pdf"])
        if variant == "short"
        else build_cv_pdf(language=language, font_family=font["pdf"])
    )
    buf = io.BytesIO(bytes(pdf.output()))
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=_cv_filename("pdf", variant),
        mimetype="application/pdf",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
