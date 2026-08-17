from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class OutputConversionError(RuntimeError):
    """Raised when a downstream converter fails."""


class OutputConverter(ABC):
    @abstractmethod
    def convert_html(self, input_path: Path, output_path: Path) -> None:
        raise NotImplementedError
