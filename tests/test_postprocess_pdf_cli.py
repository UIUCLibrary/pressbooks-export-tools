"""Tests for the pb-postprocess-pdf CLI command."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner

from pressbooks_export.cli import postprocess_pdf

pikepdf = pytest.importorskip("pikepdf")


_SAMPLE_HTML_WITH_MATH = """\
<html>
<body>
<p><math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math></p>
</body>
</html>
"""


def _make_minimal_pdf(path: Path) -> None:
    """Write a minimal valid PDF to *path*."""
    pdf = pikepdf.new()
    page = pikepdf.Page(
        pikepdf.Dictionary(
            Type=pikepdf.Name.Page,
            MediaBox=pikepdf.Array([0, 0, 612, 792]),
        )
    )
    pdf.pages.append(page)
    pdf.save(str(path))


class TestPostprocessPdfCommand:
    """Tests for the postprocess_pdf Click command."""

    def test_overwrites_in_place_by_default(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "book.pdf"
        _make_minimal_pdf(pdf_path)

        runner = CliRunner()
        result = runner.invoke(postprocess_pdf, [str(pdf_path)])

        assert result.exit_code == 0, result.output
        assert "PDF/UA-2 post-processing complete" in result.output
        assert str(pdf_path) in result.output

        with pikepdf.open(str(pdf_path)) as pdf:
            assert pdf.Root["/ViewerPreferences"]["/DisplayDocTitle"] is True
            xmp = pdf.Root["/Metadata"].read_bytes().decode()
            assert "<pdfuaid:part>2</pdfuaid:part>" in xmp

    def test_writes_to_output_path_when_specified(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "input.pdf"
        out_path = tmp_path / "output.pdf"
        _make_minimal_pdf(pdf_path)

        runner = CliRunner()
        result = runner.invoke(postprocess_pdf, [str(pdf_path), "--output", str(out_path)])

        assert result.exit_code == 0, result.output
        assert out_path.exists()
        assert str(out_path) in result.output

    def test_help_text_mentions_pikepdf(self) -> None:
        """The command help text should mention pikepdf so users know what to install."""
        runner = CliRunner()
        result = runner.invoke(postprocess_pdf, ["--help"])
        assert result.exit_code == 0
        assert "pikepdf" in result.output

    def test_output_path_in_success_message(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "source.pdf"
        out_path = tmp_path / "result.pdf"
        _make_minimal_pdf(pdf_path)

        runner = CliRunner()
        result = runner.invoke(postprocess_pdf, [str(pdf_path), "--output", str(out_path)])

        assert result.exit_code == 0
        assert str(out_path) in result.output
        # Input path should NOT appear as the "complete" target.
        assert "PDF/UA-2 post-processing complete" in result.output


def _make_tagged_pdf_with_formula(path: Path) -> None:
    """Write a minimal tagged PDF containing one Formula structure element."""
    pdf = pikepdf.new()
    page = pikepdf.Page(
        pikepdf.Dictionary(
            Type=pikepdf.Name.Page,
            MediaBox=pikepdf.Array([0, 0, 612, 792]),
        )
    )
    pdf.pages.append(page)

    formula_elem = pdf.make_indirect(
        pikepdf.Dictionary(
            S=pikepdf.Name("/Formula"),
            P=pikepdf.Dictionary(),
        )
    )
    struct_root = pdf.make_indirect(
        pikepdf.Dictionary(
            Type=pikepdf.Name("/StructTreeRoot"),
            K=pikepdf.Array([formula_elem]),
        )
    )
    pdf.Root["/MarkInfo"] = pikepdf.Dictionary(Marked=True)
    pdf.Root["/StructTreeRoot"] = struct_root
    pdf.save(str(path))


class TestPostprocessPdfHtmlOption:
    """Tests for the --html option on pb-postprocess-pdf."""

    def test_html_option_injects_mathml_af(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "book.pdf"
        html_path = tmp_path / "clean.html"
        _make_tagged_pdf_with_formula(pdf_path)
        html_path.write_text(_SAMPLE_HTML_WITH_MATH, encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            postprocess_pdf, [str(pdf_path), "--html", str(html_path)]
        )

        assert result.exit_code == 0, result.output
        assert "PDF/UA-2 post-processing complete" in result.output

        with pikepdf.open(str(pdf_path)) as pdf:
            from pressbooks_export.converters.pdf_mathml_postprocessor import (
                _find_formula_elements,
            )
            formulas = _find_formula_elements(pdf)
            assert len(formulas) == 1
            assert "/AF" in formulas[0]

    def test_html_option_no_math_prints_warning(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "book.pdf"
        html_path = tmp_path / "clean.html"
        _make_minimal_pdf(pdf_path)
        html_path.write_text("<html><body><p>no math here</p></body></html>", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            postprocess_pdf, [str(pdf_path), "--html", str(html_path)]
        )

        assert result.exit_code == 0
        assert "No <math> elements" in result.output

    def test_html_option_help_text(self) -> None:
        runner = CliRunner()
        result = runner.invoke(postprocess_pdf, ["--help"])
        assert result.exit_code == 0
        assert "--html" in result.output


def _make_tagged_pdf_with_figures(path: Path, num_figures: int = 2) -> None:
    """Write a minimal tagged PDF containing Figure structure elements."""
    pdf = pikepdf.new()
    page = pikepdf.Page(
        pikepdf.Dictionary(
            Type=pikepdf.Name.Page,
            MediaBox=pikepdf.Array([0, 0, 612, 792]),
        )
    )
    pdf.pages.append(page)

    figure_elems = [
        pdf.make_indirect(
            pikepdf.Dictionary(S=pikepdf.Name("/Figure"), P=pikepdf.Dictionary())
        )
        for _ in range(num_figures)
    ]
    struct_root = pdf.make_indirect(
        pikepdf.Dictionary(
            Type=pikepdf.Name("/StructTreeRoot"),
            K=pikepdf.Array(figure_elems),
        )
    )
    pdf.Root["/MarkInfo"] = pikepdf.Dictionary(Marked=True)
    pdf.Root["/StructTreeRoot"] = struct_root
    pdf.save(str(path))


_SAMPLE_HTML_WITH_LATEX_IMAGES = """\
<html>
<body>
<p><img class="latex" alt="x+y" /></p>
<p><img class="latex" alt="\\\\frac{1}{2}" /></p>
</body>
</html>
"""


class TestGentlePipelineAutoDetect:
    """The --html option auto-detects image-only HTML and injects into Figures."""

    def test_latex_images_trigger_figure_injection(self, tmp_path: Path) -> None:
        """When HTML has <img class="latex"> images, MathML is injected into Figures."""
        pdf_path = tmp_path / "book.pdf"
        html_path = tmp_path / "clean.html"
        _make_tagged_pdf_with_figures(pdf_path, num_figures=2)
        html_path.write_text(_SAMPLE_HTML_WITH_LATEX_IMAGES, encoding="utf-8")

        stub_mathml = [
            '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>',
            '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>y</mi></math>',
        ]

        with mock.patch(
            "pressbooks_export.cli.extract_mathml_from_latex_images",
            return_value=stub_mathml,
        ) as mock_extract, mock.patch(
            "pressbooks_export.cli.inject_mathml_into_figures",
            return_value=2,
        ) as mock_inject:
            runner = CliRunner()
            result = runner.invoke(
                postprocess_pdf, [str(pdf_path), "--html", str(html_path)]
            )

        assert result.exit_code == 0, result.output
        mock_extract.assert_called_once()
        mock_inject.assert_called_once()
        assert "Figure element(s)" in result.output

    def test_math_elements_still_use_formula_injection(self, tmp_path: Path) -> None:
        """HTML with <math> elements still injects into Formula elements (not Figure)."""
        pdf_path = tmp_path / "book.pdf"
        html_path = tmp_path / "clean.html"
        _make_tagged_pdf_with_formula(pdf_path)
        html_path.write_text(_SAMPLE_HTML_WITH_MATH, encoding="utf-8")

        with mock.patch(
            "pressbooks_export.cli.inject_mathml_into_figures"
        ) as mock_figure_inject:
            runner = CliRunner()
            result = runner.invoke(
                postprocess_pdf, [str(pdf_path), "--html", str(html_path)]
            )

        assert result.exit_code == 0, result.output
        mock_figure_inject.assert_not_called()
        assert "Formula element(s)" in result.output
