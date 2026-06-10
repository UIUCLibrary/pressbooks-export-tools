"""Tests that nested MathML structures survive the full pipeline to PDF output.

These tests verify the complete pipeline from LaTeX images through to the
final tagged PDF:

1. The HTML processor correctly converts nested LaTeX images into nested MathML.
2. The Pandoc + LuaLaTeX converter produces a tagged PDF with proper structure.
3. Formula structure elements in the PDF contain <math> child nodes (not plain text).

The PDF structure tests require Pandoc and LuaLaTeX with PDF/UA-2 tagging
support (TeX Live 2025+).  They are skipped in environments that lack these
tools.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

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


def _has_tagged_pdf_support() -> bool:
    """Return True if the environment can produce tagged PDFs with math tagging.

    This requires Pandoc, LuaLaTeX, and TeX Live with ``\\DocumentMetadata``
    ``tagging=on, testphase=math`` support (TeX Live 2025+).
    """
    if not shutil.which("pandoc"):
        return False
    lualatex = shutil.which("lualatex-dev") or shutil.which("lualatex")
    if not lualatex:
        return False

    # Compile a minimal doc with tagging=on to see if it actually produces tags
    import tempfile
    test_tex = (
        "\\DocumentMetadata{tagging=on,testphase=math,lang=en}\n"
        "\\documentclass{article}\n"
        "\\usepackage{amsmath}\n"
        "\\begin{document}\n"
        "$x^2$\n"
        "\\end{document}\n"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / "probe.tex"
        tex_path.write_text(test_tex)
        result = subprocess.run(
            [lualatex, "-interaction=nonstopmode", f"-output-directory={tmpdir}", str(tex_path)],
            capture_output=True, text=True,
        )
        pdf_path = Path(tmpdir) / "probe.pdf"
        if result.returncode != 0 or not pdf_path.exists():
            return False
        try:
            import pikepdf
            pdf = pikepdf.open(pdf_path)
            return "/StructTreeRoot" in pdf.Root
        except Exception:
            return False


_tagged_pdf_available = _has_tagged_pdf_support()
requires_tagged_pdf = pytest.mark.skipif(
    not _tagged_pdf_available,
    reason="Requires Pandoc + LuaLaTeX with PDF/UA-2 tagging support (TeX Live 2025+)",
)


def _walk_struct_tree(node: Any) -> list[tuple[str, Any]]:
    """Walk the PDF structure tree and yield (tag_name, node) pairs."""
    results: list[tuple[str, Any]] = []

    def _recurse(n: Any) -> None:
        import pikepdf
        if isinstance(n, pikepdf.Array):
            for child in n:
                _recurse(child)
            return
        if isinstance(n, pikepdf.Dictionary):
            tag = str(n.get("/S", "")) if "/S" in n else ""
            results.append((tag, n))
            if "/K" in n:
                _recurse(n["/K"])

    _recurse(node)
    return results


def _find_formula_nodes(pdf_path: Path) -> list[Any]:
    """Find all Formula structure elements in a tagged PDF."""
    import pikepdf
    pdf = pikepdf.open(pdf_path)
    root = pdf.Root
    if "/StructTreeRoot" not in root:
        return []
    struct_root = root["/StructTreeRoot"]
    if "/K" not in struct_root:
        return []
    all_nodes = _walk_struct_tree(struct_root["/K"])
    return [node for tag, node in all_nodes if "Formula" in tag]


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
# PDF structure tests – verify the *final* PDF contains proper math tagging
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tagged_pdf_path(processed_html: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate a tagged PDF via PandocLuaLatexPdfConverter and return its path."""
    from pressbooks_export.converters.pdf import PandocLuaLatexPdfConverter

    tmp_dir = tmp_path_factory.mktemp("tagged_pdf")
    html_path = tmp_dir / "input.html"
    html_path.write_text(processed_html, encoding="utf-8")

    pdf_path = tmp_dir / "output.pdf"
    PandocLuaLatexPdfConverter().convert_html(html_path, pdf_path)
    return pdf_path


@requires_tagged_pdf
def test_pdf_is_tagged(tagged_pdf_path: Path) -> None:
    """The generated PDF must be a tagged PDF with a StructTreeRoot."""
    import pikepdf
    pdf = pikepdf.open(tagged_pdf_path)
    assert "/StructTreeRoot" in pdf.Root, (
        "PDF is not tagged – StructTreeRoot missing. "
        "Ensure LuaLaTeX with tagging support (TeX Live 2025+) is used."
    )


@requires_tagged_pdf
def test_pdf_has_formula_elements(tagged_pdf_path: Path) -> None:
    """The tagged PDF must contain Formula structure elements for math."""
    formulas = _find_formula_nodes(tagged_pdf_path)
    assert len(formulas) > 0, (
        "No Formula structure elements found in the PDF. "
        "Math content is not being tagged as formulas."
    )


@requires_tagged_pdf
def test_formula_has_math_child(tagged_pdf_path: Path) -> None:
    """Each Formula element must have a <math> node as its first child.

    This is the key accessibility requirement: the Formula structure element
    in the tagged PDF must contain an embedded MathML tree (via Associated
    Files or direct structure), not just plain text content.  When
    ``testphase=math`` is active, luamml converts LaTeX math to MathML and
    attaches it to the Formula structure element.
    """
    import pikepdf

    formulas = _find_formula_nodes(tagged_pdf_path)
    assert len(formulas) > 0, "No Formula elements found – cannot verify math children"

    for i, formula in enumerate(formulas):
        # Check for Associated Files (AF) containing MathML – this is how
        # luamml embeds MathML in PDF/UA-2.
        has_af = "/AF" in formula
        # Also check for a child structure element with /S = /math
        has_math_child = False
        if "/K" in formula:
            children = formula["/K"]
            if isinstance(children, pikepdf.Dictionary):
                children = [children]
            elif isinstance(children, pikepdf.Array):
                children = list(children)
            else:
                children = []
            for child in children:
                if isinstance(child, pikepdf.Dictionary) and "/S" in child:
                    tag = str(child["/S"])
                    if "math" in tag.lower():
                        has_math_child = True
                        break

        assert has_af or has_math_child, (
            f"Formula element {i} has neither an Associated File (AF) with MathML "
            f"nor a <math> child structure element.  The Formula tag contains only "
            f"plain text.  Ensure the LuaLaTeX template includes "
            f"'testphase=math' in \\DocumentMetadata to activate luamml."
        )
