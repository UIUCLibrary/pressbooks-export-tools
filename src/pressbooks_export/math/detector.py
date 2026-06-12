from __future__ import annotations

from dataclasses import dataclass

from lxml import html


@dataclass(slots=True)
class LatexImage:
    element: html.HtmlElement
    latex: str
    display: bool
    src: str | None


def _is_display(element: html.HtmlElement) -> bool:
    """Return True if *element* represents a display-mode equation.

    Pressbooks HTML exports signal display mode via the parent element's CSS
    classes rather than an attribute on the ``<img>`` itself.  The two
    patterns seen in real exports are:

    * ``<div class="display-math"><img .../></div>``
    * ``<span class="math display"><img .../></span>``

    A ``data-display="block"`` attribute on the element itself is also
    accepted as a fallback for hand-crafted or legacy markup.
    """
    parent = element.getparent()
    if parent is not None:
        parent_classes = set((parent.get("class") or "").split())
        if "display-math" in parent_classes:
            return True
        if "display" in parent_classes and "math" in parent_classes:
            return True
    return element.get("data-display", "inline").lower() == "block"


def find_latex_images(document: html.HtmlElement) -> list[LatexImage]:
    matches: list[LatexImage] = []
    for element in document.xpath('//img[contains(concat(" ", normalize-space(@class), " "), " latex ")]'):
        latex = (element.get("alt") or "").strip()
        if not latex:
            continue
        matches.append(
            LatexImage(
                element=element,
                latex=latex,
                display=_is_display(element),
                src=element.get("src"),
            )
        )
    return matches
