from __future__ import annotations

from pathlib import Path

from .base import OutputConversionError, OutputConverter


class WeasyPrintPdfConverter(OutputConverter):
    def convert_html(self, input_path: Path, output_path: Path) -> None:
        try:
            from weasyprint import HTML
        except ImportError as exc:  # pragma: no cover - import guard
            raise OutputConversionError(
                "WeasyPrint is not installed. Install the '[pdf]' extra to enable PDF export."
            ) from exc
        HTML(filename=str(input_path)).write_pdf(str(output_path))
