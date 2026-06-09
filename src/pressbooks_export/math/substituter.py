from __future__ import annotations

from lxml import etree, html

from .backends.base import MathBackend
from .detector import LatexImage


def replace_latex_images(
    document: html.HtmlElement,
    math_images: list[LatexImage],
    backend: MathBackend,
) -> None:
    for math_image in math_images:
        mathml = backend.convert(math_image.latex, display=math_image.display)
        replacement = html.fragment_fromstring(mathml, create_parent=False)
        if math_image.display:
            replacement.set("display", "block")
        parent = math_image.element.getparent()
        if parent is None:
            continue
        parent.replace(math_image.element, replacement)
        etree.strip_attributes(replacement, "data-source-src")
