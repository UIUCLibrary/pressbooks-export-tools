from __future__ import annotations

from .backends.base import MathBackend


class MathConverter:
    """Thin wrapper around the selected math backend."""

    def __init__(self, backend: MathBackend) -> None:
        self.backend = backend

    def convert(self, latex: str, *, display: bool = False) -> str:
        return self.backend.convert(latex, display=display)
