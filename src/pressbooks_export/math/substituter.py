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
        The MathML ``alttext`` attribute is always set to the original LaTeX
        source regardless of whether spoken descriptions are provided, so that
        Prince XML can populate the Formula structure element's Alt entry.
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


_MML_NS = "http://www.w3.org/1998/Math/MathML"


def _fix_mover_stretchy(root: etree._Element) -> None:
    """Remove erroneous ``stretchy="true"`` from accent ``<mo>`` inside ``<mover>``.

    latex2mathml incorrectly sets ``stretchy="true"`` on certain single-character
    accent operators (e.g. the macron for ``\\bar{x}``, the arrow for
    ``\\vec{x}``).  MathJax — and the MathML Core specification — treat these as
    *accent* operators whose stretchy default is ``false``.  The explicit
    ``stretchy="true"`` overrides that default, causing the glyph to expand to
    the full width of its container and appear far above the base character.

    The fix sets ``stretchy="false"`` explicitly on the accent ``<mo>``.
    Simply deleting the attribute is insufficient for Prince XML, which does
    not apply the MathML operator-dictionary default of ``false`` for accent
    operators inside ``<mover>`` — without the explicit value the glyph still
    expands to fill its container and floats above the base character.

    The "wide" operators (``\\widehat``, ``\\overline``, ``\\overbrace``, etc.)
    do *not* have ``stretchy`` set at all (neither latex2mathml nor MathJax sets
    it for them), so they are unaffected by this function and continue to stretch
    as intended.
    """
    # lxml may strip MathML namespace declarations when parsing via
    # html.fragment_fromstring, leaving bare tag names (e.g. "mover" instead of
    # "{http://...}mover").  Support both forms by matching the local name.
    for el in root.iter():
        local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if local != "mover":
            continue
        children = list(el)
        # <mover> has exactly two children: base (index 0) and accent (index 1).
        if len(children) < 2:
            continue
        accent_mo = children[1]
        mo_local = accent_mo.tag.split("}")[-1] if "}" in accent_mo.tag else accent_mo.tag
        if mo_local == "mo" and accent_mo.get("stretchy") == "true":
            accent_mo.set("stretchy", "false")


def _apply_replacement(
    math_image: LatexImage,
    mathml: str,
    index: int,
    speeches: list[str] | None,
) -> None:
    """Swap *math_image*'s ``<img>`` element for the parsed *mathml* fragment."""
    replacement = html.fragment_fromstring(mathml, create_parent=False)
    _fix_mover_stretchy(replacement)
    if math_image.display:
        replacement.set("display", "block")
    # Prince XML reads the MathML ``alttext`` attribute to populate the
    # Formula structure element's Alt entry in the PDF.  When a spoken
    # description is available, use it as ``alttext`` so Acrobat and screen
    # readers see the plain-English text rather than raw LaTeX.  The original
    # LaTeX is preserved in ``data-latex`` for downstream use (e.g. MathML
    # re-conversion or debugging).  When no spoken description is available,
    # fall back to the LaTeX source so Prince still has an Alt value.
    spoken = speeches[index] if (speeches and index < len(speeches)) else ""
    if not replacement.get("alttext"):
        if spoken:
            replacement.set("alttext", spoken)
        elif math_image.latex:
            replacement.set("alttext", math_image.latex)
    # Always preserve the original LaTeX in data-latex when spoken alt text is
    # active so downstream consumers can still access the source expression,
    # even when the backend already emitted its own alttext value.
    if spoken and math_image.latex and not replacement.get("data-latex"):
        replacement.set("data-latex", math_image.latex)
    if spoken:
        replacement.set("aria-label", spoken)
    parent = math_image.element.getparent()
    if parent is None:
        return
    # Preserve the tail (text between this element and its next sibling) so
    # that surrounding prose such as " or " between two consecutive inline
    # equations is not silently dropped when the <img> is replaced.
    replacement.tail = math_image.element.tail
    parent.replace(math_image.element, replacement)
    etree.strip_attributes(replacement, "data-source-src")
