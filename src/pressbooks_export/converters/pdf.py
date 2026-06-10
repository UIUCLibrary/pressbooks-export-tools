from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from .base import OutputConversionError, OutputConverter

logger = logging.getLogger(__name__)

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


def _kpsewhich(package: str) -> str | None:
    """Look up a TeX package file via ``kpsewhich``.

    Returns the resolved path or *None* when the binary is missing or the
    package is not found.
    """
    kpsewhich = shutil.which("kpsewhich")
    if not kpsewhich:
        return None
    try:
        result = subprocess.run(
            [kpsewhich, package],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def check_pdf_math_dependencies(*, warn_fn: object | None = None) -> list[str]:
    """Check for dependencies required for MathML in tagged PDFs.

    Returns a list of human-readable warning strings for any missing or
    problematic dependencies.  An empty list means all checks passed.

    Parameters
    ----------
    warn_fn:
        Optional callable that receives each warning string as it is
        discovered (e.g. ``click.echo`` or ``logging.warning``).  When
        *None*, warnings are only collected in the returned list.
    """
    warnings: list[str] = []

    def _warn(msg: str) -> None:
        warnings.append(msg)
        if callable(warn_fn):
            warn_fn(msg)

    # -- pandoc ----------------------------------------------------------------
    if not shutil.which("pandoc"):
        _warn(
            "WARNING: pandoc is not installed. "
            "Install pandoc (https://pandoc.org/) to enable PDF export."
        )

    # -- lualatex / lualatex-dev -----------------------------------------------
    has_dev = shutil.which("lualatex-dev")
    has_stable = shutil.which("lualatex")
    if not has_dev and not has_stable:
        _warn(
            "WARNING: Neither lualatex-dev nor lualatex found on PATH. "
            "Install TeX Live 2025+ to enable PDF export."
        )
    elif not has_dev:
        _warn(
            "WARNING: lualatex-dev not found; falling back to lualatex. "
            "lualatex-dev (TeX Live 2025+) is recommended for full "
            "PDF/UA-2 math tagging support."
        )

    # -- luamml ----------------------------------------------------------------
    if not _kpsewhich("luamml.sty"):
        _warn(
            "WARNING: luamml.sty not found in your TeX installation. "
            "The luamml package is required for MathML tagging in PDFs. "
            "Without it, Formula tags in the PDF will contain plain text "
            "instead of <math> structure. "
            "Install it with: tlmgr install luamml"
        )

    # -- tagpdf ----------------------------------------------------------------
    if not _kpsewhich("tagpdf.sty"):
        _warn(
            "WARNING: tagpdf.sty not found in your TeX installation. "
            "The tagpdf package is required for PDF tagging/accessibility. "
            "Install it with: tlmgr install tagpdf"
        )

    # -- DocumentMetadata / tagging support ------------------------------------
    ltx = has_dev or has_stable
    if ltx:
        probe_tex = (
            "\\DocumentMetadata{tagging=on,lang=en}\n"
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "test\n"
            "\\end{document}\n"
        )
        try:
            result = subprocess.run(
                [ltx, "-interaction=nonstopmode", "-halt-on-error", "-jobname=probe"],
                input=probe_tex,
                capture_output=True,
                text=True,
                timeout=30,
                cwd="/tmp",
            )
            if result.returncode != 0:
                # Check for the specific "tagging key unknown" error
                if "tagging" in result.stderr or "tagging" in result.stdout:
                    _warn(
                        "WARNING: Your LuaLaTeX does not support "
                        "\\DocumentMetadata{tagging=on}. "
                        "PDF tagging (and MathML in Formula tags) requires "
                        "TeX Live 2025+ or a development release. "
                        "Current lualatex may be too old."
                    )
                else:
                    _warn(
                        "WARNING: LuaLaTeX probe compilation failed. "
                        "PDF tagging support could not be verified. "
                        "Ensure TeX Live 2025+ is installed."
                    )
        except (OSError, subprocess.TimeoutExpired):
            pass

    return warnings


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
        - luamml TeX package (for MathML in Formula structure elements)
        - tagpdf TeX package (for PDF tagging infrastructure)
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
