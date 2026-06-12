"""Extract LaTeX expressions from a Pressbooks HTML export and write a CSV.

Each row in the output CSV contains:

* ``latex``   — the raw LaTeX string from the ``alt`` attribute.
* ``display`` — ``"block"`` for display-mode equations, ``"inline"`` otherwise.
* ``speech``  — plain-English spoken description produced by Speech Rule Engine
                (empty string when the SRE backend is not available).
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path

from lxml import html

from .math.backends.sre_backend import SpeechConversionError, SreNodeBackend
from .math.detector import _is_display

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LatexEntry:
    latex: str
    display: bool
    speech: str = field(default="")

    @property
    def display_label(self) -> str:
        return "block" if self.display else "inline"


def _find_latex_images(
    document: html.HtmlElement,
    classes: list[str],
) -> list[tuple[str, bool]]:
    """Return ``(latex, display)`` tuples for every matching ``<img>`` element.

    An ``<img>`` matches when its ``class`` attribute contains **all** of the
    names in *classes*.

    Parameters
    ----------
    document:
        Parsed lxml HTML document.
    classes:
        List of class names that must all be present on the ``<img>`` element.
    """
    results: list[tuple[str, bool]] = []
    for element in document.xpath("//img"):
        element_classes = set((element.get("class") or "").split())
        if not all(c in element_classes for c in classes):
            continue
        latex = (element.get("alt") or "").strip()
        if not latex:
            continue
        display = _is_display(element)
        results.append((latex, display))
    return results


def extract_latex(
    html_content: str,
    *,
    classes: list[str] | None = None,
    sre_backend: SreNodeBackend | None = None,
) -> list[LatexEntry]:
    """Parse *html_content* and return a :class:`LatexEntry` for every match.

    Parameters
    ----------
    html_content:
        Raw HTML string (e.g. from reading a Pressbooks export file).
    classes:
        Class names the ``<img>`` element must have.  Defaults to
        ``["latex", "mathjax"]``.
    sre_backend:
        Speech backend to use.  A default :class:`SreNodeBackend` is
        constructed when *None*.  Pass an instance to override the script
        path or node binary, or to inject a test double.
    """
    if classes is None:
        classes = ["latex", "mathjax"]
    if sre_backend is None:
        sre_backend = SreNodeBackend()

    document = html.fromstring(html_content)
    matches = _find_latex_images(document, classes)

    entries: list[LatexEntry] = []
    if not matches:
        return entries

    speeches: list[str] = [""] * len(matches)
    try:
        speeches = sre_backend.to_speech_batch(matches)
    except SpeechConversionError as exc:
        logger.warning("SRE batch conversion failed: %s", exc)

    for (latex, display), speech in zip(matches, speeches):
        entries.append(LatexEntry(latex=latex, display=display, speech=speech))
    return entries


def write_csv(entries: list[LatexEntry], output_path: Path) -> None:
    """Write *entries* to a CSV file at *output_path*.

    Columns: ``latex``, ``display``, ``speech``.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["latex", "display", "speech"])
        writer.writeheader()
        for entry in entries:
            writer.writerow(
                {
                    "latex": entry.latex,
                    "display": entry.display_label,
                    "speech": entry.speech,
                }
            )
