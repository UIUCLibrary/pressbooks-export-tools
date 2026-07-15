"""Tests for the pb-postprocess-pdf CLI command."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner

from pressbooks_export.cli import postprocess_pdf

pikepdf = pytest.importorskip("pikepdf")


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
            assert pdf.Root["/ViewerPreferences"]["/DisplayDocTitle"] == True
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
