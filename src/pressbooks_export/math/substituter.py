from __future__ import annotations

import logging

from lxml import etree, html

from .backends.base import MathBackend, MathConversionError
from .detector import LatexImage

logger = logging.getLogger(__name__)


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
        Math conversion backend that turns LaTeX into MathML strings.  When
        the backend exposes a ``convert_batch`` method, all equations are
        converted in a single call for efficiency.  Equations that fail
        individually are left as their original ``<img>`` placeholder so that
        the rest of the document is not affected.
    speeches:
        Optional list of plain-English spoken descriptions, one per entry in
        *math_images* (same order).  When provided and non-empty, each spoken
        description is set as the ``aria-label`` attribute on the generated
        ``<math>`` element, giving assistive technology a human-readable
        fallback without requiring it to navigate the full MathML tree.
    """
    if not math_images:
        return

    # Prefer batch conversion when the backend supports it (e.g. MathJax):
    # all equations are processed in a single subprocess call rather than one
    # call per equation.
    convert_batch = getattr(backend, "convert_batch", None)
    if callable(convert_batch):
        items = [(img.latex, img.display) for img in math_images]
        try:
            batch_results: list[str | MathConversionError] = convert_batch(items)
        except MathConversionError as exc:
            logger.warning("MathML batch conversion failed entirely, falling back to per-equation: %s", exc)
            batch_results = []

        if len(batch_results) == len(math_images):
            for i, (math_image, result) in enumerate(zip(math_images, batch_results)):
                if isinstance(result, MathConversionError):
                    logger.warning("MathML conversion failed for %r: %s", math_image.latex[:40], result)
                    continue
                _apply_replacement(math_image, result, i, speeches)
            return
        # Fall through to per-equation path if batch returned unexpected length.

    for i, math_image in enumerate(math_images):
        try:
            mathml = backend.convert(math_image.latex, display=math_image.display)
        except MathConversionError as exc:
            logger.warning("MathML conversion failed for %r: %s", math_image.latex[:40], exc)
            continue
        _apply_replacement(math_image, mathml, i, speeches)


def _apply_replacement(
    math_image: LatexImage,
    mathml: str,
    index: int,
    speeches: list[str] | None,
) -> None:
    """Swap *math_image*'s ``<img>`` element for the parsed *mathml* fragment."""
    replacement = html.fragment_fromstring(mathml, create_parent=False)
    if math_image.display:
        replacement.set("display", "block")
    if speeches and index < len(speeches) and speeches[index]:
        replacement.set("aria-label", speeches[index])
    parent = math_image.element.getparent()
    if parent is None:
        return
    parent.replace(math_image.element, replacement)
    etree.strip_attributes(replacement, "data-source-src")
