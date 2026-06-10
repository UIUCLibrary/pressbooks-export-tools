from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import OutputConversionError, OutputConverter


class PandocLuaLatexPdfConverter(OutputConverter):
    """PDF converter using Pandoc with LuaLaTeX engine for proper math rendering.

    This is the recommended converter for documents containing mathematical equations.
    It converts HTML with MathML to LaTeX and compiles with LuaLaTeX, producing
    properly rendered math in the output PDF.

    Requirements:
        - pandoc (https://pandoc.org/)
        - LuaLaTeX (texlive-luatex package)
    """

    def convert_html(self, input_path: Path, output_path: Path) -> None:
        pandoc_binary = shutil.which("pandoc")
        if not pandoc_binary:
            raise OutputConversionError(
                "Pandoc is not installed. Install pandoc to enable PDF export."
            )

        lualatex_binary = shutil.which("lualatex")
        if not lualatex_binary:
            raise OutputConversionError(
                "LuaLaTeX is not installed. Install texlive-luatex to enable PDF export."
            )

        result = subprocess.run(
            [pandoc_binary, str(input_path), "-o", str(output_path), "--pdf-engine=lualatex"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise OutputConversionError(f"Pandoc conversion failed: {result.stderr}")


class WeasyPrintPdfConverter(OutputConverter):
    """Legacy PDF converter using WeasyPrint.

    Warning:
        WeasyPrint does not have native MathML support. Math expressions will not
        render correctly. Use PandocLuaLatexPdfConverter for documents with math.

    This converter may still be useful for simple documents without mathematical
    content where a pure-Python solution is preferred.
    """

    def convert_html(self, input_path: Path, output_path: Path) -> None:
        try:
            from weasyprint import HTML
        except ImportError as exc:  # pragma: no cover - import guard
            raise OutputConversionError(
                "WeasyPrint is not installed. Install the '[pdf]' extra to enable PDF export."
            ) from exc
        HTML(filename=str(input_path)).write_pdf(str(output_path))
