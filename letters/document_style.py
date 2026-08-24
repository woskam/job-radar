"""
Shared letterhead styling for generated documents (cover letters and CV):
a header/footer band with name/address/date/contact info in a muted gray,
matching the dashboard's own palette. Used by dashboard/app.py's letter
downloads and letters/cv_builder.py's CV downloads so both stay visually
consistent without duplicating this code.
"""

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from matching.scorer import load_profile

SENDER = load_profile()["sender"]

# Same muted gray as the dashboard itself (--muted: #6E6A63), so downloads
# visually match the same look and feel.
MUTED_RGB = (0x6E, 0x6A, 0x63)
MUTED_HEX = "6E6A63"

# Font options for downloads -- deliberately limited to PDF's built-in base
# fonts (no separate .ttf files to bundle/embed) paired with a
# style-matching, universally available Word font.
FONT_OPTIONS = {
    "helvetica": {"label": "Modern (Helvetica/Arial)", "pdf": "Helvetica", "docx": "Arial"},
    "times": {"label": "Classic (Times New Roman)", "pdf": "Times", "docx": "Times New Roman"},
    "courier": {"label": "Typewriter (Courier)", "pdf": "Courier", "docx": "Courier New"},
}
DEFAULT_FONT = "helvetica"

MONTH_NAMES = {
    "nl": ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
}


def format_date(language: str) -> str:
    today = date.today()
    month = MONTH_NAMES.get(language, MONTH_NAMES["en"])[today.month - 1]
    if language == "nl":
        return f"{today.day} {month} {today.year}"
    return f"{month} {today.day}, {today.year}"


def docx_add_hyperlink(paragraph, url: str, text: str, font_name: str = None, size: float = None):
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
    # A hyperlink's <w:r> is nested inside <w:hyperlink>, not a direct child
    # of the paragraph, so python-docx's paragraph.runs can't see it to style
    # it afterwards the normal way -- font/size have to be set here instead.
    if font_name:
        rfonts = OxmlElement("w:rFonts")
        rfonts.set(qn("w:ascii"), font_name)
        rfonts.set(qn("w:hAnsi"), font_name)
        rpr.append(rfonts)
    if size is not None:
        sz = OxmlElement("w:sz")
        sz.set(qn("w:val"), str(int(size * 2)))  # half-points
        rpr.append(sz)
    run.append(rpr)
    text_el = OxmlElement("w:t")
    text_el.text = text
    run.append(text_el)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def docx_add_border(paragraph, side: str):
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


def build_docx_header(section, language: str, subject: str, font_name: str):
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
    date_run = date_p.add_run(format_date(language))
    date_run.font.size = Pt(9)
    date_run.font.color.rgb = muted
    date_run.font.name = font_name

    address_p = header.add_paragraph()
    address_run = address_p.add_run(SENDER["address"])
    address_run.font.size = Pt(9)
    address_run.font.color.rgb = muted
    address_run.font.name = font_name

    contact_p = header.add_paragraph()
    docx_add_hyperlink(contact_p, f"mailto:{SENDER['email']}", SENDER["email"])
    sep_run = contact_p.add_run("  ·  ")
    sep_run.font.size = Pt(9)
    sep_run.font.color.rgb = muted
    docx_add_hyperlink(contact_p, f"https://{SENDER['url']}", SENDER["url"])
    for run in contact_p.runs:
        run.font.size = Pt(9)
        run.font.name = font_name

    subject_p = header.add_paragraph()
    subject_run = subject_p.add_run(subject)
    subject_run.bold = True
    subject_run.font.size = Pt(10)
    subject_run.font.color.rgb = muted
    subject_run.font.name = font_name
    docx_add_border(subject_p, "bottom")


def build_docx_footer(section, font_name: str):
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
    docx_add_border(line_p, "top")


def make_letterhead_pdf(font_family: str, language: str, subject: str):
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    class LetterheadPDF(FPDF):
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
            self.cell(0, 5, format_date(language), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

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

    pdf = LetterheadPDF()
    # cp1252 (a strict latin-1 superset) so em/en dashes, curly quotes, and a
    # bullet dot ("•") render correctly -- core PDF fonts mangle those under
    # strict latin-1.
    pdf.core_fonts_encoding = "cp1252"
    pdf.alias_nb_pages()
    return pdf


def docx_add_bullet(doc, text: str, font_name: str, size: float = 11, indent_pt: float = 16):
    """
    A real hanging-indent bullet paragraph: left_indent places wrapped lines,
    first_line_indent pulls the bullet mark back out of that, and the tab
    stop makes the text start exactly at left_indent regardless of the
    bullet glyph's width -- a plain "- text" or "•  text" prefix would only
    indent the first line, not the wraps.
    """
    from docx.shared import Pt

    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Pt(indent_pt)
    p.paragraph_format.first_line_indent = Pt(-indent_pt)
    p.paragraph_format.tab_stops.add_tab_stop(Pt(indent_pt))
    mark_run = p.add_run("•\t")
    mark_run.font.name = font_name
    mark_run.font.size = Pt(size)
    text_run = p.add_run(text)
    text_run.font.name = font_name
    text_run.font.size = Pt(size)
    return p


def pdf_add_bullet(pdf, text: str, font_family: str, size: float = 11, line_height: float = 6, bullet_indent: float = 5):
    """
    Prints the bullet mark as its own cell (advancing x, same y), then the
    body text as a separate multi_cell -- giving a true hanging indent where
    every wrapped line lines up with the bullet TEXT, not the bullet mark
    itself (embedding "•  text" as one string only indents the first line).
    Explicit align="L": fpdf2's multi_cell defaults to justified text, which
    stretches word-spacing awkwardly on wrapped lines.
    """
    from fpdf.enums import XPos, YPos

    pdf.set_font(font_family, "", size)
    pdf.cell(bullet_indent, line_height, "•")
    pdf.multi_cell(0, line_height, text, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def render_text_blocks(text: str, add_paragraph, add_bullet) -> None:
    """
    Splits `text` into blank-line-separated blocks, then within each block
    treats "- " lines as bullets (rendered via add_bullet(text)) and any
    consecutive non-bullet lines as one paragraph (joined with a space,
    rendered via add_paragraph(text)). Handles a lead-in sentence directly
    followed by bullets with no blank line in between -- how the letter
    generator actually writes them (a single "\\n", not "\\n\\n", between
    "Some evidence:" and the first "- ..." line).
    """
    for block in text.split("\n\n"):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        buffer: list[str] = []
        for line in lines:
            if line.startswith("- "):
                if buffer:
                    add_paragraph(" ".join(buffer))
                    buffer = []
                add_bullet(line[2:])
            else:
                buffer.append(line)
        if buffer:
            add_paragraph(" ".join(buffer))


INLINE_MARKUP_RE = re.compile(r"\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)]+)\)")


def parse_inline_markup(text: str) -> list[dict]:
    """
    Splits "plain **bold** [link text](https://example.com) plain" into
    fragments: [{"text": ..., "bold": bool, "link": str | None}, ...].
    Deliberately simple and non-nested -- CV/letter content never needs bold
    and a link in the same span.
    """
    fragments = []
    pos = 0
    for m in INLINE_MARKUP_RE.finditer(text):
        if m.start() > pos:
            fragments.append({"text": text[pos:m.start()], "bold": False, "link": None})
        if m.group(1) is not None:
            fragments.append({"text": m.group(1), "bold": True, "link": None})
        else:
            fragments.append({"text": m.group(2), "bold": False, "link": m.group(3)})
        pos = m.end()
    if pos < len(text):
        fragments.append({"text": text[pos:], "bold": False, "link": None})
    return fragments or [{"text": "", "bold": False, "link": None}]


def docx_add_inline_runs(paragraph, text: str, font_name: str, size: float = None) -> None:
    """
    Adds runs for parse_inline_markup(text)'s fragments to an existing
    paragraph -- bold spans render bold, link spans render as a real
    hyperlink (docx_add_hyperlink) instead of visible raw URL text.
    """
    from docx.shared import Pt

    for frag in parse_inline_markup(text):
        if not frag["text"]:
            continue
        if frag["link"]:
            docx_add_hyperlink(paragraph, frag["link"], frag["text"], font_name=font_name, size=size)
        else:
            run = paragraph.add_run(frag["text"])
            run.bold = frag["bold"]
            run.font.name = font_name
            if size is not None:
                run.font.size = Pt(size)


def pdf_write_inline(pdf, text: str, font_family: str, size: float, line_height: float) -> None:
    """
    Writes parse_inline_markup(text)'s fragments with pdf.write(), which
    flows at the current position and wraps back to the page's left margin
    like normal text -- bold spans switch to a bold font, link spans use
    write()'s own `link` param so the fragment is clickable without a
    visible raw URL. Caller is responsible for the trailing pdf.ln(...).
    """
    for frag in parse_inline_markup(text):
        if not frag["text"]:
            continue
        pdf.set_font(font_family, "B" if frag["bold"] else "", size)
        pdf.write(line_height, frag["text"], link=frag["link"] or "")
