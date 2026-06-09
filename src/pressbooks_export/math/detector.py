from __future__ import annotations

from dataclasses import dataclass

from lxml import html


@dataclass(slots=True)
class LatexImage:
    element: html.HtmlElement
    latex: str
    display: bool
    src: str | None


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
                display=element.get("data-display", "inline").lower() == "block",
                src=element.get("src"),
            )
        )
    return matches
