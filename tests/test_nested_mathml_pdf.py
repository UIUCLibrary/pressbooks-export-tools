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

@pytest.fixture(scope="module")
def processed_html() -> str:
    """Run the full HtmlProcessor pipeline on the nested MathML fixture (cached)."""
    markup = NESTED_HTML.read_text(encoding="utf-8")
    return HtmlProcessor(backend=Latex2MathMLBackend()).process_html(markup)


@pytest.fixture(scope="module")
def processed_doc(processed_html: str) -> html.HtmlElement:
    return html.document_fromstring(processed_html)


# Minimum expected size for a PDF containing math content.
_MIN_PDF_SIZE_BYTES = 2500


# ---------------------------------------------------------------------------
# Detection tests – nested LaTeX images are found correctly
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fixture_doc() -> html.HtmlElement:
    return html.document_fromstring(NESTED_HTML.read_text(encoding="utf-8"))


def test_fixture_detects_four_latex_images(fixture_doc: html.HtmlElement) -> None:
    """The fixture has 4 latex images (5th has no alt and should be skipped)."""
    images = find_latex_images(fixture_doc)
    assert len(images) == 4


def test_fixture_detects_display_modes(fixture_doc: html.HtmlElement) -> None:
    images = find_latex_images(fixture_doc)
    # First two are inline, last two are block
    assert [img.display for img in images] == [False, False, True, True]


# ---------------------------------------------------------------------------
# MathML substitution tests – nested structures are present after processing
# ---------------------------------------------------------------------------


def test_processed_html_contains_no_latex_images_with_alt(
    processed_doc: html.HtmlElement,
) -> None:
    """All latex images *with alt text* should be replaced; alt-less ones remain."""
    remaining = processed_doc.xpath(
        '//img[contains(concat(" ", normalize-space(@class), " "), " latex ")]'
    )
    # Only the one without alt text should remain
    assert len(remaining) == 1
    assert not (remaining[0].get("alt") or "").strip()


def test_processed_html_has_math_elements(processed_doc: html.HtmlElement) -> None:
    math_els = processed_doc.xpath('//*[local-name()="math"]')
    assert len(math_els) == 4


def test_nested_fraction_has_mfrac_inside_mfrac(
    processed_doc: html.HtmlElement,
) -> None:
    """\\frac{\\frac{a}{b}}{c} should produce <mfrac> containing <mfrac>."""
    math_els = processed_doc.xpath('//*[local-name()="math"]')
    first_math = math_els[0]
    outer_fracs = first_math.xpath('.//*[local-name()="mfrac"]')
    assert len(outer_fracs) >= 2, "Expected nested mfrac elements"
    # The inner mfrac should be a descendant of the outer mfrac
    inner = outer_fracs[0].xpath('.//*[local-name()="mfrac"]')
    assert len(inner) >= 1, "Inner mfrac not found inside outer mfrac"


def test_nested_sqrt_contains_mfrac(processed_doc: html.HtmlElement) -> None:
    """\\sqrt{\\frac{...}{...}} should produce <msqrt> containing <mfrac>."""
    math_els = processed_doc.xpath('//*[local-name()="math"]')
    second_math = math_els[1]
    sqrts = second_math.xpath('.//*[local-name()="msqrt"]')
    assert len(sqrts) >= 1, "Expected msqrt element"
    fracs_in_sqrt = sqrts[0].xpath('.//*[local-name()="mfrac"]')
    assert len(fracs_in_sqrt) >= 1, "Expected mfrac inside msqrt"


def test_matrix_has_mtable(processed_doc: html.HtmlElement) -> None:
    """Matrix should produce <mtable> with <mtr> and <mtd>."""
    math_els = processed_doc.xpath('//*[local-name()="math"]')
    third_math = math_els[2]
    tables = third_math.xpath('.//*[local-name()="mtable"]')
    assert len(tables) >= 1, "Expected mtable element for matrix"
    rows = tables[0].xpath('.//*[local-name()="mtr"]')
    assert len(rows) >= 2, "Expected at least 2 rows in matrix"


def test_complex_nested_has_msubsup_and_mfrac_and_msqrt(
    processed_doc: html.HtmlElement,
) -> None:
    """\\sum_{i=1}^{n} \\frac{x_i^2}{\\sqrt{...}} should have msubsup, mfrac, msqrt."""
    math_els = processed_doc.xpath('//*[local-name()="math"]')
    fourth_math = math_els[3]
    assert fourth_math.xpath('.//*[local-name()="msubsup"]'), "Expected msubsup"
    assert fourth_math.xpath('.//*[local-name()="mfrac"]'), "Expected mfrac"
    assert fourth_math.xpath('.//*[local-name()="msqrt"]'), "Expected msqrt"


def test_block_display_math_has_display_attribute(
    processed_doc: html.HtmlElement,
) -> None:
    """Block-mode equations should have display='block' on the <math> element."""
    math_els = processed_doc.xpath('//*[local-name()="math"]')
    # 3rd and 4th are block display
    for idx in (2, 3):
        assert math_els[idx].get("display") == "block", (
            f"Math element {idx} should have display='block'"
        )


# ---------------------------------------------------------------------------
# PDF output tests – WeasyPrint generates a non-trivial PDF
# ---------------------------------------------------------------------------


def test_weasyprint_produces_pdf_from_nested_mathml(
    tmp_path: Path, processed_html: str,
) -> None:
    """WeasyPrint should generate a PDF without crashing on nested MathML."""
    from weasyprint import HTML

    pdf_path = tmp_path / "nested_math.pdf"
    HTML(string=processed_html).write_pdf(str(pdf_path))

    assert pdf_path.exists()
    size = pdf_path.stat().st_size
    assert size > 0, "PDF file is empty"
    assert size > _MIN_PDF_SIZE_BYTES, (
        f"PDF suspiciously small ({size} bytes), content may be missing"
    )


def test_weasyprint_pdf_is_valid(tmp_path: Path, processed_html: str) -> None:
    """The generated PDF should be a valid PDF file."""
    from weasyprint import HTML

    pdf_path = tmp_path / "nested_math.pdf"
    HTML(string=processed_html).write_pdf(str(pdf_path))

    pdf_bytes = pdf_path.read_bytes()
    assert pdf_bytes[:5] == b"%PDF-", "File should start with PDF header"
    assert b"%%EOF" in pdf_bytes[-128:], "File should end with EOF marker"
