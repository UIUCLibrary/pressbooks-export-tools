"""Tests for the PDF MathML post-processor.

These tests verify that MathML strings can be extracted from processed HTML
and injected as Associated Files on Formula structure elements in a tagged PDF.

Since producing a tagged PDF requires TeX Live 2025+, most tests use a
synthetic tagged PDF built with pikepdf to exercise the injection logic
without external tool dependencies.
"""

from __future__ import annotations

from pathlib import Path

import pikepdf
import pytest

from pressbooks_export.converters.pdf_mathml_postprocessor import (
    extract_mathml_from_html,
    extract_mathml_from_latex_images,
    inject_mathml_into_figures,
    inject_mathml_into_pdf,
    _find_formula_elements,
    _find_struct_elements,
)


# ---------------------------------------------------------------------------
# extract_mathml_from_html tests
# ---------------------------------------------------------------------------

SAMPLE_HTML = """\
<html>
<body>
<p>Inline: <math xmlns="http://www.w3.org/1998/Math/MathML">
  <mfrac><mi>a</mi><mi>b</mi></mfrac>
</math></p>
<p>Block: <math xmlns="http://www.w3.org/1998/Math/MathML" display="block">
  <msqrt><mi>x</mi></msqrt>
</math></p>
</body>
</html>
"""


def test_extract_mathml_returns_one_string_per_math_element() -> None:
    result = extract_mathml_from_html(SAMPLE_HTML)
    assert len(result) == 2


def test_extract_mathml_contains_math_tags() -> None:
    result = extract_mathml_from_html(SAMPLE_HTML)
    for mathml in result:
        assert "<math" in mathml
        assert "</math>" in mathml


def test_extract_mathml_preserves_nested_structure() -> None:
    result = extract_mathml_from_html(SAMPLE_HTML)
    assert "mfrac" in result[0]
    assert "msqrt" in result[1]


def test_extract_mathml_returns_empty_for_no_math() -> None:
    result = extract_mathml_from_html("<html><body><p>No math</p></body></html>")
    assert result == []


# ---------------------------------------------------------------------------
# Helpers to build synthetic tagged PDFs
# ---------------------------------------------------------------------------


def _make_tagged_pdf_with_formulas(
    pdf_path: Path,
    num_formulas: int = 2,
) -> None:
    """Create a minimal tagged PDF with Formula structure elements."""
    pdf = pikepdf.new()
    page = pikepdf.Page(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name.Page,
                "/MediaBox": pikepdf.Array([0, 0, 612, 792]),
            }
        )
    )
    pdf.pages.append(page)

    # Build structure tree with Formula elements
    formula_dicts = []
    for i in range(num_formulas):
        formula = pdf.make_indirect(
            pikepdf.Dictionary(
                {
                    "/Type": pikepdf.Name("/StructElem"),
                    "/S": pikepdf.Name.Formula,
                    "/K": pikepdf.Array([]),
                }
            )
        )
        formula_dicts.append(formula)

    doc_elem = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/StructElem"),
                "/S": pikepdf.Name("/Document"),
                "/K": pikepdf.Array(formula_dicts),
            }
        )
    )
    # Set parent references
    for f in formula_dicts:
        f["/P"] = doc_elem

    struct_tree = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/StructTreeRoot"),
                "/K": doc_elem,
            }
        )
    )
    doc_elem["/P"] = struct_tree

    pdf.Root["/StructTreeRoot"] = struct_tree
    pdf.Root["/MarkInfo"] = pikepdf.Dictionary(
        {"/Marked": pikepdf.Boolean(True)}
    )

    pdf.save(pdf_path)
    pdf.close()


# ---------------------------------------------------------------------------
# inject_mathml_into_pdf tests
# ---------------------------------------------------------------------------


def test_inject_into_tagged_pdf_adds_af_to_formulas(tmp_path: Path) -> None:
    """MathML should be injected as AF on each Formula element."""
    pdf_path = tmp_path / "tagged.pdf"
    _make_tagged_pdf_with_formulas(pdf_path, num_formulas=2)

    mathml = [
        '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>a</mi></math>',
        '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>b</mi></math>',
    ]
    updated = inject_mathml_into_pdf(pdf_path, mathml)
    assert updated == 2

    # Verify the PDF now has AF entries on Formula elements
    pdf = pikepdf.open(pdf_path)
    formulas = _find_formula_elements(pdf)
    assert len(formulas) == 2
    for formula in formulas:
        assert "/AF" in formula, "Formula should have an AF entry after injection"
        af = formula["/AF"]
        assert isinstance(af, pikepdf.Array)
        assert len(af) >= 1
        # Verify the AF contains a filespec with MathML
        spec = af[0]
        assert "/EF" in spec
        ef_stream = spec["/EF"]["/F"]
        content = ef_stream.read_bytes().decode("utf-8")
        assert "<math" in content
    pdf.close()


def test_inject_reads_mathml_content_correctly(tmp_path: Path) -> None:
    """The injected AF content should match the original MathML string."""
    pdf_path = tmp_path / "tagged.pdf"
    _make_tagged_pdf_with_formulas(pdf_path, num_formulas=1)

    mathml_str = '<math xmlns="http://www.w3.org/1998/Math/MathML"><mfrac><mi>x</mi><mi>y</mi></mfrac></math>'
    inject_mathml_into_pdf(pdf_path, [mathml_str])

    pdf = pikepdf.open(pdf_path)
    formulas = _find_formula_elements(pdf)
    af_stream = formulas[0]["/AF"][0]["/EF"]["/F"]
    content = af_stream.read_bytes().decode("utf-8")
    assert "mfrac" in content
    assert "<mi>x</mi>" in content
    pdf.close()


def test_inject_skips_formulas_with_existing_mathml_af(tmp_path: Path) -> None:
    """Formulas that already have MathML AFs should not be modified."""
    pdf_path = tmp_path / "tagged.pdf"
    _make_tagged_pdf_with_formulas(pdf_path, num_formulas=1)

    mathml = ['<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>a</mi></math>']

    # First injection
    updated1 = inject_mathml_into_pdf(pdf_path, mathml)
    assert updated1 == 1

    # Second injection should skip (already has AF)
    updated2 = inject_mathml_into_pdf(pdf_path, mathml)
    assert updated2 == 0


def test_inject_handles_more_formulas_than_mathml(tmp_path: Path) -> None:
    """When there are more formulas than MathML strings, inject what we have."""
    pdf_path = tmp_path / "tagged.pdf"
    _make_tagged_pdf_with_formulas(pdf_path, num_formulas=3)

    mathml = ['<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>a</mi></math>']
    updated = inject_mathml_into_pdf(pdf_path, mathml)
    assert updated == 1


def test_inject_returns_zero_for_untagged_pdf(tmp_path: Path) -> None:
    """An untagged PDF should produce zero updates."""
    pdf_path = tmp_path / "untagged.pdf"
    pdf = pikepdf.new()
    pdf.pages.append(
        pikepdf.Page(
            pikepdf.Dictionary(
                {
                    "/Type": pikepdf.Name.Page,
                    "/MediaBox": pikepdf.Array([0, 0, 612, 792]),
                }
            )
        )
    )
    pdf.save(pdf_path)
    pdf.close()

    mathml = ['<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>']
    updated = inject_mathml_into_pdf(pdf_path, mathml)
    assert updated == 0


def test_inject_writes_to_separate_output_path(tmp_path: Path) -> None:
    """When output_path differs from pdf_path, original should be unchanged."""
    pdf_path = tmp_path / "input.pdf"
    out_path = tmp_path / "output.pdf"
    _make_tagged_pdf_with_formulas(pdf_path, num_formulas=1)

    original_size = pdf_path.stat().st_size

    mathml = ['<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>z</mi></math>']
    updated = inject_mathml_into_pdf(pdf_path, mathml, output_path=out_path)
    assert updated == 1
    assert out_path.exists()
    # Output should be larger than input (has AF now)
    assert out_path.stat().st_size > original_size


def test_formula_af_has_supplement_relationship(tmp_path: Path) -> None:
    """The AF filespec should have /AFRelationship /Supplement."""
    pdf_path = tmp_path / "tagged.pdf"
    _make_tagged_pdf_with_formulas(pdf_path, num_formulas=1)

    mathml = ['<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>q</mi></math>']
    inject_mathml_into_pdf(pdf_path, mathml)

    pdf = pikepdf.open(pdf_path)
    formulas = _find_formula_elements(pdf)
    spec = formulas[0]["/AF"][0]
    assert str(spec["/AFRelationship"]) == "/Supplement"
    pdf.close()


# ---------------------------------------------------------------------------
# extract_mathml_from_latex_images tests (gentle pipeline)
# ---------------------------------------------------------------------------

_LATEX_IMAGE_HTML = """\
<html>
<body>
<p><img class="latex" alt="x+y" /></p>
<p><img class="latex" alt="\\frac{1}{2}" /></p>
</body>
</html>
"""


class StubMathBackend:
    """Math backend test double: wraps LaTeX in a trivial <math> fragment."""

    def convert(self, latex: str, *, display: bool = False) -> str:
        display_attr = ' display="block"' if display else ''
        return (
            f'<math xmlns="http://www.w3.org/1998/Math/MathML"{display_attr}>'
            f'<mtext>{latex}</mtext></math>'
        )

    def convert_batch(
        self, items: list[tuple[str, bool]]
    ) -> list[str]:
        return [self.convert(latex, display=display) for latex, display in items]


def test_extract_mathml_from_latex_images_returns_one_per_image() -> None:
    result = extract_mathml_from_latex_images(_LATEX_IMAGE_HTML, backend=StubMathBackend())
    assert len(result) == 2


def test_extract_mathml_from_latex_images_contains_math_tags() -> None:
    result = extract_mathml_from_latex_images(_LATEX_IMAGE_HTML, backend=StubMathBackend())
    for mathml in result:
        assert "<math" in mathml
        assert "</math>" in mathml


def test_extract_mathml_from_latex_images_preserves_latex() -> None:
    result = extract_mathml_from_latex_images(_LATEX_IMAGE_HTML, backend=StubMathBackend())
    assert "x+y" in result[0]
    assert "frac" in result[1]


def test_extract_mathml_from_latex_images_returns_empty_for_no_images() -> None:
    result = extract_mathml_from_latex_images(
        "<html><body><p>no math</p></body></html>",
        backend=StubMathBackend(),
    )
    assert result == []


def test_extract_mathml_from_latex_images_uses_data_latex_over_alt() -> None:
    """data-latex (spoken-alt pipeline) should be preferred over alt."""
    html = (
        '<html><body>'
        '<p><img class="latex" alt="spoken text" data-latex="x^2" /></p>'
        '</body></html>'
    )
    result = extract_mathml_from_latex_images(html, backend=StubMathBackend())
    assert len(result) == 1
    assert "x^2" in result[0]
    assert "spoken text" not in result[0]


# ---------------------------------------------------------------------------
# inject_mathml_into_figures tests (gentle pipeline)
# ---------------------------------------------------------------------------

def _make_tagged_pdf_with_figure_elements(
    pdf_path: Path, num_figures: int = 2
) -> None:
    """Create a minimal tagged PDF with Figure structure elements."""
    pdf = pikepdf.new()
    page = pikepdf.Page(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name.Page,
                "/MediaBox": pikepdf.Array([0, 0, 612, 792]),
            }
        )
    )
    pdf.pages.append(page)

    figure_dicts = []
    for _ in range(num_figures):
        fig = pdf.make_indirect(
            pikepdf.Dictionary(
                {
                    "/Type": pikepdf.Name("/StructElem"),
                    "/S": pikepdf.Name("/Figure"),
                    "/K": pikepdf.Array([]),
                }
            )
        )
        figure_dicts.append(fig)

    doc_elem = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/StructElem"),
                "/S": pikepdf.Name("/Document"),
                "/K": pikepdf.Array(figure_dicts),
            }
        )
    )
    for f in figure_dicts:
        f["/P"] = doc_elem

    struct_tree = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/StructTreeRoot"),
                "/K": doc_elem,
            }
        )
    )
    doc_elem["/P"] = struct_tree
    pdf.Root["/StructTreeRoot"] = struct_tree
    pdf.Root["/MarkInfo"] = pikepdf.Dictionary({"/Marked": pikepdf.Boolean(True)})
    pdf.save(pdf_path)
    pdf.close()


def test_inject_into_figures_adds_af(tmp_path: Path) -> None:
    """MathML should be injected as AF on each Figure element."""
    pdf_path = tmp_path / "tagged.pdf"
    _make_tagged_pdf_with_figure_elements(pdf_path, num_figures=2)

    mathml = [
        '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>a</mi></math>',
        '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>b</mi></math>',
    ]
    updated = inject_mathml_into_figures(pdf_path, mathml)
    assert updated == 2

    with pikepdf.open(pdf_path) as pdf:
        figures = _find_struct_elements(pdf, "Figure")
        assert len(figures) == 2
        for fig in figures:
            assert "/AF" in fig
            content = fig["/AF"][0]["/EF"]["/F"].read_bytes().decode("utf-8")
            assert "<math" in content


def test_inject_into_figures_skips_empty_strings(tmp_path: Path) -> None:
    """Empty MathML strings (failed conversions) should be skipped."""
    pdf_path = tmp_path / "tagged.pdf"
    _make_tagged_pdf_with_figure_elements(pdf_path, num_figures=2)

    mathml = ["", '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>b</mi></math>']
    updated = inject_mathml_into_figures(pdf_path, mathml)
    assert updated == 1


def test_find_struct_elements_matches_figure_not_formula(tmp_path: Path) -> None:
    """_find_struct_elements with 'Figure' should not return Formula elements."""
    pdf_path = tmp_path / "mixed.pdf"
    pdf = pikepdf.new()
    page = pikepdf.Page(
        pikepdf.Dictionary(
            {"/Type": pikepdf.Name.Page, "/MediaBox": pikepdf.Array([0, 0, 612, 792])}
        )
    )
    pdf.pages.append(page)
    fig = pdf.make_indirect(
        pikepdf.Dictionary({"/Type": pikepdf.Name("/StructElem"), "/S": pikepdf.Name("/Figure")})
    )
    formula = pdf.make_indirect(
        pikepdf.Dictionary({"/Type": pikepdf.Name("/StructElem"), "/S": pikepdf.Name("/Formula")})
    )
    struct_tree = pdf.make_indirect(
        pikepdf.Dictionary(
            {"/Type": pikepdf.Name("/StructTreeRoot"), "/K": pikepdf.Array([fig, formula])}
        )
    )
    pdf.Root["/StructTreeRoot"] = struct_tree
    pdf.save(pdf_path)
    pdf.close()

    with pikepdf.open(pdf_path) as pdf:
        figures = _find_struct_elements(pdf, "Figure")
        formulas = _find_struct_elements(pdf, "Formula")
    assert len(figures) == 1
    assert len(formulas) == 1
