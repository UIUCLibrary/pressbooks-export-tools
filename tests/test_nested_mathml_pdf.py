"""Tests that nested MathML structures survive the full pipeline to PDF output.

WeasyPrint does not *render* MathML correctly, but it does include the text
content of MathML elements in the generated PDF.  These tests verify that:

1. The HTML processor correctly converts nested LaTeX images into nested MathML.
2. WeasyPrint can produce a non-empty PDF from the resulting HTML.
3. The nested MathML element structure is present in the processed HTML.

This gives confidence that the pipeline does not silently drop or corrupt
deeply nested math content on the way to PDF output.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import html

from pressbooks_export.html_processor import HtmlProcessor
from pressbooks_export.math.backends.latex2mathml_backend import Latex2MathMLBackend
from pressbooks_export.math.detector import find_latex_images

FIXTURES = Path(__file__).parent / "fixtures"
NESTED_HTML = FIXTURES / "nested_mathml.html"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _process_nested_fixture() -> str:
    """Run the full HtmlProcessor pipeline on the nested MathML fixture."""
    markup = NESTED_HTML.read_text(encoding="utf-8")
    return HtmlProcessor(backend=Latex2MathMLBackend()).process_html(markup)


def _parse(processed: str) -> html.HtmlElement:
    return html.document_fromstring(processed)


# ---------------------------------------------------------------------------
# Detection tests – nested LaTeX images are found correctly
# ---------------------------------------------------------------------------


def test_fixture_detects_four_latex_images() -> None:
    """The fixture has 4 latex images (5th has no alt and should be skipped)."""
    doc = html.document_fromstring(NESTED_HTML.read_text(encoding="utf-8"))
    images = find_latex_images(doc)
    assert len(images) == 4


def test_fixture_detects_display_modes() -> None:
    doc = html.document_fromstring(NESTED_HTML.read_text(encoding="utf-8"))
    images = find_latex_images(doc)
    # First two are inline, last two are block
    assert [img.display for img in images] == [False, False, True, True]


# ---------------------------------------------------------------------------
# MathML substitution tests – nested structures are present after processing
# ---------------------------------------------------------------------------


def test_processed_html_contains_no_latex_images_with_alt() -> None:
    """All latex images *with alt text* should be replaced; alt-less ones remain."""
    processed = _process_nested_fixture()
    doc = _parse(processed)
    remaining = doc.xpath(
        '//img[contains(concat(" ", normalize-space(@class), " "), " latex ")]'
    )
    # Only the one without alt text should remain
    assert len(remaining) == 1
    assert not (remaining[0].get("alt") or "").strip()


def test_processed_html_has_math_elements() -> None:
    processed = _process_nested_fixture()
    doc = _parse(processed)
    math_els = doc.xpath('//*[local-name()="math"]')
    assert len(math_els) == 4


def test_nested_fraction_has_mfrac_inside_mfrac() -> None:
    """\\frac{\\frac{a}{b}}{c} should produce <mfrac> containing <mfrac>."""
    processed = _process_nested_fixture()
    doc = _parse(processed)
    math_els = doc.xpath('//*[local-name()="math"]')
    first_math = math_els[0]
    outer_fracs = first_math.xpath('.//*[local-name()="mfrac"]')
    assert len(outer_fracs) >= 2, "Expected nested mfrac elements"
    # The inner mfrac should be a descendant of the outer mfrac
    inner = outer_fracs[0].xpath('.//*[local-name()="mfrac"]')
    assert len(inner) >= 1, "Inner mfrac not found inside outer mfrac"


def test_nested_sqrt_contains_mfrac() -> None:
    """\\sqrt{\\frac{...}{...}} should produce <msqrt> containing <mfrac>."""
    processed = _process_nested_fixture()
    doc = _parse(processed)
    math_els = doc.xpath('//*[local-name()="math"]')
    second_math = math_els[1]
    sqrts = second_math.xpath('.//*[local-name()="msqrt"]')
    assert len(sqrts) >= 1, "Expected msqrt element"
    fracs_in_sqrt = sqrts[0].xpath('.//*[local-name()="mfrac"]')
    assert len(fracs_in_sqrt) >= 1, "Expected mfrac inside msqrt"


def test_matrix_has_mtable() -> None:
    """Matrix should produce <mtable> with <mtr> and <mtd>."""
    processed = _process_nested_fixture()
    doc = _parse(processed)
    math_els = doc.xpath('//*[local-name()="math"]')
    third_math = math_els[2]
    tables = third_math.xpath('.//*[local-name()="mtable"]')
    assert len(tables) >= 1, "Expected mtable element for matrix"
    rows = tables[0].xpath('.//*[local-name()="mtr"]')
    assert len(rows) >= 2, "Expected at least 2 rows in matrix"


def test_complex_nested_has_msubsup_and_mfrac_and_msqrt() -> None:
    """\\sum_{i=1}^{n} \\frac{x_i^2}{\\sqrt{...}} should have msubsup, mfrac, msqrt."""
    processed = _process_nested_fixture()
    doc = _parse(processed)
    math_els = doc.xpath('//*[local-name()="math"]')
    fourth_math = math_els[3]
    assert fourth_math.xpath('.//*[local-name()="msubsup"]'), "Expected msubsup"
    assert fourth_math.xpath('.//*[local-name()="mfrac"]'), "Expected mfrac"
    assert fourth_math.xpath('.//*[local-name()="msqrt"]'), "Expected msqrt"


def test_block_display_math_has_display_attribute() -> None:
    """Block-mode equations should have display='block' on the <math> element."""
    processed = _process_nested_fixture()
    doc = _parse(processed)
    math_els = doc.xpath('//*[local-name()="math"]')
    # 3rd and 4th are block display
    for idx in (2, 3):
        assert math_els[idx].get("display") == "block", (
            f"Math element {idx} should have display='block'"
        )


# ---------------------------------------------------------------------------
# PDF output tests – WeasyPrint generates a non-trivial PDF
# ---------------------------------------------------------------------------


def test_weasyprint_produces_pdf_from_nested_mathml(tmp_path: Path) -> None:
    """WeasyPrint should generate a PDF without crashing on nested MathML."""
    from weasyprint import HTML

    processed = _process_nested_fixture()
    pdf_path = tmp_path / "nested_math.pdf"
    HTML(string=processed).write_pdf(str(pdf_path))

    assert pdf_path.exists()
    size = pdf_path.stat().st_size
    assert size > 0, "PDF file is empty"
    # A PDF with math content should be larger than a minimal empty PDF (~2.5KB)
    assert size > 2500, f"PDF suspiciously small ({size} bytes), content may be missing"


def test_weasyprint_pdf_is_valid(tmp_path: Path) -> None:
    """The generated PDF should be a valid PDF file."""
    from weasyprint import HTML

    processed = _process_nested_fixture()
    pdf_path = tmp_path / "nested_math.pdf"
    HTML(string=processed).write_pdf(str(pdf_path))

    pdf_bytes = pdf_path.read_bytes()
    assert pdf_bytes[:5] == b"%PDF-", "File should start with PDF header"
    assert b"%%EOF" in pdf_bytes[-128:], "File should end with EOF marker"
