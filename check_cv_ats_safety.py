#!/usr/bin/env python3
"""
Local, offline sanity check for whether the short CV's PDF output is safe
for an ATS resume parser to read: renders letters/cv_short.yaml (and
cv_short_nl.yaml, if present) to PDF via letters/cv_short_builder.py, reads
the text back out with pypdf, and warns about any bullet/entry/skill whose
content doesn't show up in the extracted text -- the signal a column, text
box, or unusual layout primitive silently dropped content that a real ATS
parser would also likely drop or garble.

This is a heuristic, not a certification: it can't reproduce any specific
vendor's actual parser, only catch the class of gross content-loss bug a
layout change could introduce. Run it by hand after touching
cv_short_builder.py or the CV data files -- it's not part of the scrape
cycle and adds no production dependency (pypdf is dev-only, used here).

Usage: python check_cv_ats_safety.py [--lang en|nl]
"""

import argparse
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from letters.cv_short_builder import CV_SHORT_PATH_NL, build_short_cv_pdf, load_short_cv_data


def _normalize(text: str) -> str:
    # Strip markup/punctuation that either doesn't render (**bold**, [link]())
    # or that the PDF template may join with a different character than a
    # plain space (e.g. "Title · Company") -- applied identically to both the
    # probe snippet and the extracted PDF text, so this never causes a
    # mismatch by itself.
    text = re.sub(r"[*\[\]()]", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _first_words(text: str, n: int = 5) -> str:
    return " ".join(_normalize(text).split()[:n])


def extract_pdf_text(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return _normalize("\n".join(page.extract_text() or "" for page in reader.pages))


def check_language(language: str) -> list[str]:
    data = load_short_cv_data(language)
    pdf = build_short_cv_pdf(language=language, data=data)
    extracted = extract_pdf_text(bytes(pdf.output()))

    warnings = []

    def check(label: str, snippet: str) -> None:
        probe = _first_words(snippet)
        if probe and probe not in extracted:
            warnings.append(f"{label}: {snippet[:70]!r}")

    for entry in data["experience"]:
        # Checked separately, not joined with a space -- the template may
        # join title/company with its own separator (e.g. "Title · Company"),
        # and a plain-space probe would false-positive on that boundary.
        check(f"experience title ({language})", entry["title"])
        check(f"experience company ({language})", entry["company"])
        for bullet in entry["bullets"]:
            check(f"bullet ({language})", bullet)

    for entry in data.get("compact_experience", []):
        check(f"compact_experience title ({language})", entry["title"])
        check(f"compact_experience company ({language})", entry["company"])
        check(f"compact_experience description ({language})", entry["description"])

    for project in data["projects"]:
        check(f"project name ({language})", project["name"])
        check(f"project description ({language})", project["description"])

    for row in data["skills_table"]:
        check(f"skills_table[{row['label']}] ({language})", row["text"])

    return warnings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lang", choices=["en", "nl"], help="Only check this language (default: both available)")
    args = parser.parse_args()

    languages = [args.lang] if args.lang else ["en"] + (["nl"] if CV_SHORT_PATH_NL.exists() else [])

    all_warnings = []
    for language in languages:
        print(f"Checking short CV ({language})...")
        warnings = check_language(language)
        all_warnings.extend(warnings)
        if warnings:
            for w in warnings:
                print(f"  WARNING -- not found in extracted PDF text -- {w}")
        else:
            print("  OK -- every bullet/entry/skill was found in the extracted PDF text.")

    if all_warnings:
        print(f"\n{len(all_warnings)} warning(s) -- see above. A real ATS parser may drop this content too.")
        sys.exit(1)
    print("\nAll clear.")


if __name__ == "__main__":
    main()
