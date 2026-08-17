"""Tests for the pb-export CLI command (main entrypoint)."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner

from pressbooks_export.cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_EXPORT_HTML = """\
<html xml:lang="en">
<body>
<p>Inline: <img class="latex" alt="x+y" /></p>
<p>Block: <img class="latex mathjax" alt="\\frac{1}{2}" /></p>
</body>
</html>
"""


def _write_input(tmp_path: Path) -> Path:
    p = tmp_path / "dirty.html"
    p.write_text(_SAMPLE_EXPORT_HTML, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# --image-only flag
# ---------------------------------------------------------------------------

class TestImageOnlyFlag:
    """The --image-only flag skips MathML substitution and keeps images intact."""

    def test_images_preserved_in_output(self, tmp_path: Path) -> None:
        """<img class="latex"> elements must still be present in --image-only output."""
        input_path = _write_input(tmp_path)
        output_path = tmp_path / "clean.html"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(input_path),
                "--format", "html",
                "--output", str(output_path),
                "--image-only",
            ],
        )

        assert result.exit_code == 0, result.output
        content = output_path.read_text(encoding="utf-8")
        assert 'class="latex"' in content
        assert "<math" not in content

    def test_no_html_processor_called(self, tmp_path: Path) -> None:
        """HtmlProcessor must not be invoked in --image-only mode."""
        input_path = _write_input(tmp_path)
        output_path = tmp_path / "clean.html"

        with mock.patch("pressbooks_export.cli.HtmlProcessor") as mock_proc:
            runner = CliRunner()
            runner.invoke(
                main,
                [
                    str(input_path),
                    "--format", "html",
                    "--output", str(output_path),
                    "--image-only",
                ],
            )
        mock_proc.assert_not_called()

    def test_image_only_with_prince_preprocess_keeps_images(self, tmp_path: Path) -> None:
        """--image-only --prince-preprocess adds role="math" but leaves images intact."""
        input_path = _write_input(tmp_path)
        output_path = tmp_path / "clean.html"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(input_path),
                "--format", "html",
                "--output", str(output_path),
                "--image-only",
                "--prince-preprocess",
            ],
        )

        assert result.exit_code == 0, result.output
        content = output_path.read_text(encoding="utf-8")
        assert 'class="latex"' in content
        assert 'role="math"' in content
        assert "<math" not in content

    def test_without_image_only_substitutes_mathml(self, tmp_path: Path) -> None:
        """Without --image-only the default pipeline converts images to <math>."""
        input_path = _write_input(tmp_path)
        output_path = tmp_path / "clean.html"

        stub_mathml = '<math><mtext>stub</mtext></math>'
        with mock.patch(
            "pressbooks_export.cli.MathJaxNodeBackend"
        ) as mock_backend_cls:
            mock_backend = mock.MagicMock()
            mock_backend.convert_batch.return_value = [stub_mathml, stub_mathml]
            mock_backend_cls.return_value = mock_backend

            runner = CliRunner()
            result = runner.invoke(
                main,
                [
                    str(input_path),
                    "--format", "html",
                    "--output", str(output_path),
                ],
            )

        assert result.exit_code == 0, result.output
        # HtmlProcessor was used (not --image-only) so <math> should appear.
        content = output_path.read_text(encoding="utf-8")
        assert "<math" in content
