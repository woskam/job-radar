import io
import os
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

from flask import Flask, redirect, render_template, request, send_file, url_for

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db.migrations import ensure_columns
from letters.generator import detect_language
from matching.scorer import load_config, load_profile, score_breakdown

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

# Font options for the download -- deliberately limited to PDF's built-in
# base fonts (no separate .ttf files to bundle/embed) paired with a
# style-matching, universally available Word font.
FONT_OPTIONS = {
    "helvetica": {"label": "Modern (Helvetica/Arial)", "pdf": "Helvetica", "docx": "Arial"},
    "times": {"label": "Classic (Times New Roman)", "pdf": "Times", "docx": "Times New Roman"},
    "courier": {"label": "Typewriter (Courier)", "pdf": "Courier", "docx": "Courier New"},
}
DEFAULT_FONT = "helvetica"

# Sender details for the header/footer on downloaded cover letters -- read
# from profile.yaml (gitignored, personal), not hardcoded here and not parsed
# out of cv.txt (too fragile).
SENDER = load_profile()["sender"]
# Same muted gray as the dashboard itself (--muted: #6E6A63), so the download
# visually matches the same look and feel.
MUTED_RGB = (0x6E, 0x6A, 0x63)
MUTED_HEX = "6E6A63"

MONTH_NAMES = {
    "nl": ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
}


def _format_date(language: str) -> str:
    today = date.today()
    month = MONTH_NAMES.get(language, MONTH_NAMES["en"])[today.month - 1]
    if language == "nl":
        return f"{today.day} {month} {today.year}"
    return f"{month} {today.day}, {today.year}"


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


def _docx_add_hyperlink(paragraph, url: str, text: str):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    part = paragraph.part
    r_id = part.relate_to(
        url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), MUTED_HEX)
    rpr.append(color)
    run.append(rpr)
    text_el = OxmlElement("w:t")
    text_el.text = text
    run.append(text_el)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def _docx_add_border(paragraph, side: str):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    border = OxmlElement(f"w:{side}")
    border.set(qn("w:val"), "single")
    border.set(qn("w:sz"), "6")
    border.set(qn("w:space"), "4")
    border.set(qn("w:color"), MUTED_HEX)
    p_bdr.append(border)
    p_pr.append(p_bdr)


def _build_docx_header(section, language: str, subject: str, font_name: str):
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    muted = RGBColor(*MUTED_RGB)
    header = section.header
    header.is_linked_to_previous = False

    name_p = header.paragraphs[0]
    run = name_p.add_run(SENDER["name"])
    run.bold = True
    run.font.size = Pt(13)
    run.font.color.rgb = muted
    run.font.name = font_name

    date_p = header.add_paragraph()
    date_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    date_run = date_p.add_run(_format_date(language))
    date_run.font.size = Pt(9)
    date_run.font.color.rgb = muted
    date_run.font.name = font_name

    address_p = header.add_paragraph()
    address_run = address_p.add_run(SENDER["address"])
    address_run.font.size = Pt(9)
    address_run.font.color.rgb = muted
    address_run.font.name = font_name

    contact_p = header.add_paragraph()
    _docx_add_hyperlink(contact_p, f"mailto:{SENDER['email']}", SENDER["email"])
    sep_run = contact_p.add_run("  ·  ")
    sep_run.font.size = Pt(9)
    sep_run.font.color.rgb = muted
    _docx_add_hyperlink(contact_p, f"https://{SENDER['url']}", SENDER["url"])
    for run in contact_p.runs:
        run.font.size = Pt(9)
        run.font.name = font_name

    subject_p = header.add_paragraph()
    subject_run = subject_p.add_run(subject)
    subject_run.bold = True
    subject_run.font.size = Pt(10)
    subject_run.font.color.rgb = muted
    subject_run.font.name = font_name
    _docx_add_border(subject_p, "bottom")


def _build_docx_footer(section, font_name: str):
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    muted = RGBColor(*MUTED_RGB)
    footer = section.footer
    footer.is_linked_to_previous = False

    line_p = footer.paragraphs[0]
    line_run = line_p.add_run(f"{SENDER['name']} · {SENDER['email']} · {SENDER['url']}")
    line_run.font.size = Pt(8)
    line_run.font.color.rgb = muted
    line_run.font.name = font_name
    line_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _docx_add_border(line_p, "top")


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

    font = _font_choice()
    language = letter["language"] or detect_language(letter["final_text"] or letter["draft"] or "")
    subject = f"Re: {job['title']} ({job['company']})"
    text = letter["final_text"] or letter["draft"] or ""

    doc = Document()
    doc.styles["Normal"].font.name = font["docx"]
    _build_docx_header(doc.sections[0], language, subject, font["docx"])
    _build_docx_footer(doc.sections[0], font["docx"])
    for paragraph in text.split("\n\n"):
        doc.add_paragraph(paragraph)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=_letter_filename(dict(job), "docx"),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def _make_letter_pdf(font_family: str, language: str, subject: str):
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    class LetterPDF(FPDF):
        def header(self):
            self.set_font(font_family, "B", 13)
            self.set_text_color(*MUTED_RGB)
            self.cell(0, 6, SENDER["name"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            self.set_font(font_family, "", 9)
            self.cell(0, 5, SENDER["address"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.cell(
                0, 5, f"{SENDER['email']}  ·  {SENDER['url']}",
                new_x=XPos.LMARGIN, new_y=YPos.NEXT, link=f"mailto:{SENDER['email']}",
            )
            self.cell(0, 5, _format_date(language), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            self.set_font(font_family, "B", 10)
            self.cell(0, 6, subject, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            self.set_draw_color(*MUTED_RGB)
            self.set_line_width(0.3)
            y = self.get_y() + 2
            self.line(self.l_margin, y, self.w - self.r_margin, y)
            self.set_y(y + 6)
            self.set_text_color(0, 0, 0)
            self.set_font(font_family, "", 11)

        def footer(self):
            self.set_y(-20)
            self.set_draw_color(*MUTED_RGB)
            self.set_line_width(0.3)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.set_y(-16)
            self.set_font(font_family, "", 8)
            self.set_text_color(*MUTED_RGB)
            self.cell(
                0, 5, f"{SENDER['name']} · {SENDER['email']} · {SENDER['url']}",
                align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
            )
            self.cell(0, 5, f"{self.page_no()}/{{nb}}", align="C")

    pdf = LetterPDF()
    pdf.alias_nb_pages()
    return pdf


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

    font = _font_choice()
    language = letter["language"] or detect_language(letter["final_text"] or letter["draft"] or "")
    text = letter["final_text"] or letter["draft"] or ""
    # Core PDF fonts only support latin-1 -- replace characters that don't fit
    # (e.g. a single non-Latin name) instead of crashing on one stray character.
    safe_text = text.encode("latin-1", "replace").decode("latin-1")
    subject = f"Re: {job['title']} ({job['company']})".encode("latin-1", "replace").decode("latin-1")

    pdf = _make_letter_pdf(font["pdf"], language, subject)
    pdf.add_page()
    pdf.set_font(font["pdf"], size=11)
    for paragraph in safe_text.split("\n\n"):
        pdf.multi_cell(0, 6, paragraph)
        pdf.ln(4)

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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
