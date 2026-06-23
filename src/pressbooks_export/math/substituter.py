from __future__ import annotations

from lxml import etree, html

from .backends.base import MathBackend
from .detector import LatexImage


def replace_latex_images(
    document: html.HtmlElement,
    math_images: list[LatexImage],
    backend: MathBackend,
    *,
    speeches: list[str] | None = None,
) -> None:
    """Replace ``<img>`` math placeholders with MathML ``<math>`` elements.

    Parameters
    ----------
    document:
        The parsed lxml HTML document (mutated in-place).
    math_images:
        LaTeX image descriptors returned by :func:`~.detector.find_latex_images`.
    backend:
        Math conversion backend that turns LaTeX into MathML strings.
    speeches:
        Optional list of plain-English spoken descriptions, one per entry in
        *math_images* (same order).  When provided and non-empty, each spoken
        description is set as the ``aria-label`` attribute on the generated
        ``<math>`` element, giving assistive technology a human-readable
        fallback without requiring it to navigate the full MathML tree.
    """
    for i, math_image in enumerate(math_images):
        mathml = backend.convert(math_image.latex, display=math_image.display)
        replacement = html.fragment_fromstring(mathml, create_parent=False)
        if math_image.display:
            replacement.set("display", "block")
        if speeches and i < len(speeches) and speeches[i]:
            replacement.set("aria-label", speeches[i])
        parent = math_image.element.getparent()
        if parent is None:
            continue
        parent.replace(math_image.element, replacement)
        etree.strip_attributes(replacement, "data-source-src")
