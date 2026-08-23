"""
Renders the plain-text CV (letters/cv.txt / cv_nl.txt) into a styled
docx/pdf document using the same letterhead as the cover letters
(letters/document_style.py). Deliberately keeps cv.txt/cv_nl.txt as plain
text -- no new structured data format -- and works off the existing,
already-consistent convention: ALL-CAPS section headings, blank-line
separated blocks, "- " bullets.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from letters.document_style import (
    MUTED_RGB,
    build_docx_footer,
    build_docx_header,
    make_letterhead_pdf,
)
from letters.generator import CV_PATH_EN, CV_PATH_NL, load_cv

CV_SUBJECT = {"en": "Curriculum Vitae", "nl": "Curriculum Vitae"}

DATE_RE = re.compile(r"\b\d{4}\b")
# A short "Label: rest" prefix, e.g. "Digital Marketing: Performance Marketing, ..."
# or "Field of graduation: Environmental Geography" -- bolds the label so
# skills/activities lines are easier to scan instead of reading as one dense
# paragraph.
LABEL_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 /&'-]{1,40}):\s*(.+)$")


def parse_cv_blocks(text: str) -> list[dict]:
    """
    Splits the CV into blank-line-separated blocks. A block that's a single
    all-caps line is a section heading; any other block is a "detail" block
    whose lines are classified as bullet ("- " prefix), subheading (contains
    " | "), meta/date (contains a 4-digit year), or plain paragraph text, in
    that order. A paragraph line starting with a short "Label: " prefix
    carries that label separately so it can be rendered bold.
    """
    blocks = []
    for raw_block in re.split(r"\n\s*\n", text.strip()):
        lines = [line.strip() for line in raw_block.strip().splitlines() if line.strip()]
        if not lines:
            continue

        if len(lines) == 1 and lines[0] == lines[0].upper() and any(c.isalpha() for c in lines[0]):
            blocks.append({"type": "heading", "text": lines[0]})
            continue

        items = []
        for line in lines:
            if line.startswith("- "):
                items.append({"kind": "bullet", "text": line[2:]})
            elif " | " in line:
                items.append({"kind": "subheading", "text": line})
            elif DATE_RE.search(line):
                items.append({"kind": "meta", "text": line})
            else:
                label_match = LABEL_RE.match(line)
                if label_match:
                    items.append({"kind": "paragraph", "text": line, "label": label_match.group(1), "rest": label_match.group(2)})
                else:
                    items.append({"kind": "paragraph", "text": line})
        blocks.append({"type": "detail", "items": items})

    return blocks


def _body_blocks(language: str) -> list[dict]:
    text = load_cv(language)
    blocks = parse_cv_blocks(text)
    # The first block is the name/address/contact line -- already shown in
    # the letterhead header, so it's dropped here rather than repeated.
    return blocks[1:]


def build_cv_docx(language: str = "en", font_name: str = "Arial"):
    from docx import Document
    from docx.shared import Pt, RGBColor

    muted = RGBColor(*MUTED_RGB)

    doc = Document()
    doc.styles["Normal"].font.name = font_name
    build_docx_header(doc.sections[0], language, CV_SUBJECT.get(language, "Curriculum Vitae"), font_name)
    build_docx_footer(doc.sections[0], font_name)

    for block in _body_blocks(language):
        if block["type"] == "heading":
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(14)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(block["text"])
            run.bold = True
            run.font.size = Pt(12)
            run.font.name = font_name
            continue

        for item in block["items"]:
            p = doc.add_paragraph()
            if item["kind"] == "subheading":
                run = p.add_run(item["text"])
                run.font.name = font_name
                run.bold = True
                run.font.size = Pt(11)
            elif item["kind"] == "meta":
                run = p.add_run(item["text"])
                run.font.name = font_name
                run.italic = True
                run.font.size = Pt(9.5)
                run.font.color.rgb = muted
            elif item["kind"] == "bullet":
                # True hanging indent: left_indent sets where wrapped lines land,
                # first_line_indent pulls the bullet mark back out of that, and
                # the tab stop makes the text start exactly at left_indent
                # regardless of the bullet glyph's width -- a plain "•  " prefix
                # would only indent the first line, not the wraps.
                p.paragraph_format.left_indent = Pt(18)
                p.paragraph_format.first_line_indent = Pt(-18)
                p.paragraph_format.tab_stops.add_tab_stop(Pt(18))
                run = p.add_run(f"•\t{item['text']}")
                run.font.name = font_name
                run.font.size = Pt(10.5)
            elif item.get("label"):
                label_run = p.add_run(f"{item['label']}: ")
                label_run.bold = True
                label_run.font.name = font_name
                label_run.font.size = Pt(10.5)
                rest_run = p.add_run(item["rest"])
                rest_run.font.name = font_name
                rest_run.font.size = Pt(10.5)
            else:
                run = p.add_run(item["text"])
                run.font.name = font_name
                run.font.size = Pt(10.5)

    return doc


BULLET_INDENT = 5
HEADING_HEIGHT = 9.5  # heading cell (6.5) + trailing ln(3)
BLOCK_GAP = 2  # trailing ln(2) after every detail block


def _wrapped_line_count(pdf, text: str, avail_width: float) -> int:
    import math

    width = pdf.get_string_width(text)
    return max(1, math.ceil(width / avail_width))


def _estimate_block_height(pdf, block: dict, font_family: str) -> float:
    """
    Estimates the printed height of a detail block, so the caller can decide
    whether it fits in the remaining space on the page -- used to keep a
    whole entry (a job, a project, a labeled skills/activities line) from
    splitting across a page break, the same way a heading is kept from being
    orphaned. Estimated via get_string_width rather than actually drawing,
    so it's close but not pixel-exact -- fine for a page-break decision.
    """
    avail = pdf.epw
    total = 0.0
    for item in block["items"]:
        if item["kind"] == "subheading":
            pdf.set_font(font_family, "B", 11)
            total += _wrapped_line_count(pdf, item["text"], avail) * 5.6
        elif item["kind"] == "meta":
            pdf.set_font(font_family, "I", 9.5)
            total += _wrapped_line_count(pdf, item["text"], avail) * 5.2
        elif item["kind"] == "bullet":
            pdf.set_font(font_family, "", 10.5)
            total += _wrapped_line_count(pdf, item["text"], avail - BULLET_INDENT) * 5.6
        elif item.get("label"):
            pdf.set_font(font_family, "", 10.5)
            total += _wrapped_line_count(pdf, f"{item['label']}: {item['rest']}", avail) * 5.6
        else:
            pdf.set_font(font_family, "", 10.5)
            total += _wrapped_line_count(pdf, item["text"], avail) * 5.6
    return total + BLOCK_GAP


def build_cv_pdf(language: str = "en", font_family: str = "Helvetica"):
    from fpdf.enums import XPos, YPos

    subject = CV_SUBJECT.get(language, "Curriculum Vitae")
    pdf = make_letterhead_pdf(font_family, language, subject)
    pdf.add_page()

    body_blocks = _body_blocks(language)

    for index, block in enumerate(body_blocks):
        if block["type"] == "heading":
            # Keep a heading together with at least its first detail block --
            # a heading alone at the bottom of a page with its content pushed
            # to the next one looks broken.
            next_block = body_blocks[index + 1] if index + 1 < len(body_blocks) else None
            needed = HEADING_HEIGHT
            if next_block and next_block["type"] == "detail":
                needed += _estimate_block_height(pdf, next_block, font_family)
            if pdf.get_y() + needed > pdf.h - pdf.b_margin:
                pdf.add_page()
            else:
                pdf.ln(1)
            pdf.set_font(font_family, "B", 12)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 6.5, block["text"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(3)
            continue

        # A later block in a multi-entry section (e.g. the 2nd+ job under
        # PROFESSIONAL EXPERIENCE) gets the same "don't split this one entry
        # across pages" treatment, independent of the heading above it.
        block_height = _estimate_block_height(pdf, block, font_family)
        if block_height <= pdf.h - pdf.t_margin - pdf.b_margin and pdf.get_y() + block_height > pdf.h - pdf.b_margin:
            pdf.add_page()

        for item in block["items"]:
            text = item["text"]
            if item["kind"] == "subheading":
                pdf.set_font(font_family, "B", 11)
                pdf.set_text_color(0, 0, 0)
                pdf.multi_cell(0, 5.6, text, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            elif item["kind"] == "meta":
                pdf.set_font(font_family, "I", 9.5)
                pdf.set_text_color(*MUTED_RGB)
                pdf.multi_cell(0, 5.2, text, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            elif item["kind"] == "bullet":
                pdf.set_font(font_family, "", 10.5)
                pdf.set_text_color(0, 0, 0)
                # Print the bullet mark as its own cell (advancing x, same y),
                # then the body text as a separate multi_cell -- same pattern as
                # the labeled-paragraph case below, which gives a true hanging
                # indent: every wrapped line lines up with the bullet TEXT, not
                # with the bullet mark itself (embedding "•  text" as one string
                # only indents the first line, not the wraps).
                pdf.cell(BULLET_INDENT, 5.6, "•")
                pdf.multi_cell(0, 5.6, text, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            elif item.get("label"):
                # write() flows text at the current position and wraps back to
                # the page's left margin like a normal paragraph -- unlike
                # cell()+multi_cell(), it doesn't lock wrapped lines to an
                # indent matching this particular label's width, which would
                # make every label line wrap to a different column.
                pdf.set_font(font_family, "B", 10.5)
                pdf.set_text_color(0, 0, 0)
                pdf.write(5.6, f"{item['label']}: ")
                pdf.set_font(font_family, "", 10.5)
                pdf.write(5.6, item["rest"])
                pdf.ln(5.6)
            else:
                pdf.set_font(font_family, "", 10.5)
                pdf.set_text_color(0, 0, 0)
                pdf.multi_cell(0, 5.6, text, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

    return pdf
