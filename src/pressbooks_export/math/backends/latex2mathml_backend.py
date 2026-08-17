from __future__ import annotations

from .base import MathBackend, MathConversionError


class Latex2MathMLBackend(MathBackend):
    """Pure-Python fallback backend."""

    def convert(self, latex: str, *, display: bool = False) -> str:
        try:
            from latex2mathml.converter import convert
        except ImportError as exc:  # pragma: no cover - import guard
            raise MathConversionError(
                "latex2mathml is not installed. Install the '[math]' extra to use this backend."
            ) from exc
        display_value = "block" if display else "inline"
        try:
            return convert(latex, display=display_value)
        except Exception as exc:
            raise MathConversionError(f"latex2mathml conversion failed: {exc}") from exc
