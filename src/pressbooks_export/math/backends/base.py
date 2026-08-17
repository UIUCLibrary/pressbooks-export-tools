from __future__ import annotations

from abc import ABC, abstractmethod


class MathConversionError(RuntimeError):
    """Raised when a math backend cannot return MathML."""


class MathBackend(ABC):
    @abstractmethod
    def convert(self, latex: str, *, display: bool = False) -> str:
        raise NotImplementedError
