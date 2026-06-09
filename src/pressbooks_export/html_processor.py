from __future__ import annotations

from pathlib import Path

from lxml import html

from .math.backends.base import MathBackend
from .math.detector import find_latex_images
from .math.substituter import replace_latex_images


class HtmlProcessor:
    """Convert exported Pressbooks math placeholders into MathML."""

    def __init__(self, backend: MathBackend) -> None:
        self.backend = backend

    def process_html(self, markup: str) -> str:
        document = html.fromstring(markup)
        replace_latex_images(document, find_latex_images(document), self.backend)
        return html.tostring(document, encoding="unicode", pretty_print=True)

    def process_file(self, path: Path) -> str:
        return self.process_html(path.read_text(encoding="utf-8"))
