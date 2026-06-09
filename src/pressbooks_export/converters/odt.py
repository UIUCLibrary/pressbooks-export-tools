from __future__ import annotations

from pathlib import Path

from .base import OutputConversionError, OutputConverter


class PandocOdtConverter(OutputConverter):
    def convert_html(self, input_path: Path, output_path: Path) -> None:
        try:
            import pypandoc
        except ImportError as exc:  # pragma: no cover - import guard
            raise OutputConversionError(
                "pypandoc is not installed. Install the '[odt]' extra to enable ODT export."
            ) from exc
        try:
            pypandoc.convert_file(str(input_path), to="odt", outputfile=str(output_path))
        except RuntimeError as exc:  # pragma: no cover - wrapper around pandoc failures
            raise OutputConversionError(str(exc)) from exc
