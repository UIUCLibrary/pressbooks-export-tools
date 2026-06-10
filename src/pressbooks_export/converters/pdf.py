from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import OutputConversionError, OutputConverter

# Custom Pandoc LaTeX template that injects \DocumentMetadata for PDF/UA-2
# tagging support.  The template is stored alongside this module.
_PANDOC_TEMPLATE = Path(__file__).with_name("ua2-template.latex")


def _find_lualatex() -> str:
    """Return the best available LuaLaTeX binary.

    ``lualatex-dev`` (TeX Live 2025+) is preferred because it includes the
    LaTeX3 tagging support required for PDF/UA-2 compliance.  Falls back to
    ``lualatex`` when the dev binary is not available.
    """
    for candidate in ("lualatex-dev", "lualatex"):
        path = shutil.which(candidate)
        if path:
            return path
    raise OutputConversionError(
        "Neither lualatex-dev nor lualatex found on PATH. "
        "Install TeX Live 2025+ (lualatex-dev preferred) to enable PDF export."
    )


class PandocLuaLatexPdfConverter(OutputConverter):
    """PDF converter using Pandoc with LuaLaTeX engine for proper math rendering.

    This is the recommended converter for documents containing mathematical equations.
    It converts HTML with MathML to LaTeX and compiles with LuaLaTeX, producing
    properly rendered math in the output PDF.

    For PDF/UA-2 compliance the converter prefers ``lualatex-dev`` and uses a
    custom Pandoc template that emits ``\\DocumentMetadata{tagging=on,
    testphase=math, pdfstandard=ua-2}`` before ``\\documentclass``.  The
    ``testphase=math`` key activates ``luamml`` so that LuaLaTeX automatically
    converts each LaTeX math expression to MathML and embeds the MathML as
    Associated Files on Formula structure elements in the tagged PDF.

    Requirements:
        - pandoc (https://pandoc.org/)
        - lualatex-dev (TeX Live 2025+, preferred) or lualatex
    """

    def convert_html(self, input_path: Path, output_path: Path) -> None:
        pandoc_binary = shutil.which("pandoc")
        if not pandoc_binary:
            raise OutputConversionError(
                "Pandoc is not installed. Install pandoc to enable PDF export."
            )

        lualatex_binary = _find_lualatex()

        cmd = [
            pandoc_binary,
            str(input_path),
            "-o",
            str(output_path),
            f"--pdf-engine={lualatex_binary}",
            f"--template={_PANDOC_TEMPLATE}",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
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
