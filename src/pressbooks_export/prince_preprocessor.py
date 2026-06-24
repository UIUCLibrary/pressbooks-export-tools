"""HTML preprocessor that prepares Pressbooks exports for Prince XML.

This module adds ``role="math"`` to math elements and optionally replaces
LaTeX ``alt`` text with plain-English spoken descriptions so that Prince XML
produces an accessible tagged PDF.

Usage::

    from pressbooks_export.prince_preprocessor import PrinceHtmlPreprocessor

    # Basic: only add role="math"
    preprocessor = PrinceHtmlPreprocessor()
    accessible_html = preprocessor.process_file(Path("export.html"))

    # With spoken alt text (requires Node.js + SRE)
    from pressbooks_export.math.backends.sre_backend import SreNodeBackend
    preprocessor = PrinceHtmlPreprocessor(sre_backend=SreNodeBackend())
    accessible_html = preprocessor.process_file(Path("export.html"))

Note
----
ARIA landmark roles for Pressbooks structural elements (TOC navigation,
chapter regions, copyright contentinfo, etc.) were prototyped but deferred
to a separate GitHub issue for evaluation before merging.
"""

from __future__ import annotations

import logging
from pathlib import Path

from lxml import html

logger = logging.getLogger(__name__)


class PrinceHtmlPreprocessor:
    """Prepare Pressbooks HTML for Prince XML accessibility tagging.

    The preprocessor makes two categories of change:

    1. **Math roles** – ``<img class="latex">`` placeholders (when present)
       and ``<math>`` elements receive ``role="math"`` so Prince tags them as
       ``Formula`` structure elements in the PDF.  When an ``<img>`` element
       is found, the original LaTeX is preserved in a ``data-latex`` attribute
       before the ``alt`` text is replaced, so that downstream MathML
       conversion can still locate the source expression.
    2. **HTML ``lang`` attribute** – If the ``<html>`` element has only
       ``xml:lang`` (XHTML heritage) but no plain ``lang``, the plain ``lang``
       attribute is added so that Prince propagates the document language to
       the PDF catalogue.

    Parameters
    ----------
    sre_backend:
        Optional Speech Rule Engine backend.  When provided, the ``alt``
        attribute on each ``<img class="latex">`` element is replaced with a
        plain-English spoken description and the original LaTeX is moved to
        ``data-latex``.  When *None* (default), ``alt`` text is left
        unchanged and only ``role="math"`` is added.
    """

    def __init__(self, *, sre_backend=None) -> None:
        self._sre_backend = sre_backend

    def process_html(self, markup: str) -> str:
        """Return *markup* with math roles and optional spoken alt text injected."""
        document = html.fromstring(markup)
        self._fix_html_lang(document)
        self._add_math_roles(document)
        return html.tostring(document, encoding="unicode", pretty_print=True)

    def process_file(self, path: Path) -> str:
        """Read *path* and return the pre-processed HTML string."""
        return self.process_html(path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fix_html_lang(document: html.HtmlElement) -> None:
        """Ensure the root ``<html>`` element has a plain ``lang`` attribute.

        Pressbooks exports are XHTML 1.1 documents that use ``xml:lang``.
        Prince (and most HTML tools) also need the plain ``lang`` attribute
        to determine the document language for PDF tagging.

        When lxml parses XHTML markup with ``html.fromstring``, it preserves
        ``xml:lang`` as a literal attribute (not a Clark-notation namespace
        attribute), so we look for ``xml:lang`` directly.
        """
        root = document if document.tag == "html" else document.find(".//html")
        if root is None:
            return
        xml_lang = root.get("xml:lang")
        if xml_lang and not root.get("lang"):
            root.set("lang", xml_lang)

    def _add_math_roles(self, document: html.HtmlElement) -> None:
        """Add ``role="math"`` to math elements and optionally update alt text.

        Handles two element types:

        * ``<img class="latex">`` – Pressbooks math placeholders that have
          not yet been converted to MathML.  Receives ``role="math"`` and,
          when an SRE backend is available, has its ``alt`` attribute replaced
          with a spoken description (original LaTeX moved to ``data-latex``).
        * ``<math>`` – Already-converted MathML elements (e.g. when this
          preprocessor runs after :class:`~pressbooks_export.html_processor.HtmlProcessor`).
          Receives ``role="math"`` if not already set.
        """
        # --- <img class="latex"> placeholders ----------------------------------
        img_elements = document.xpath(
            '//img[contains(concat(" ", normalize-space(@class), " "), " latex ")]'
        )

        if img_elements and self._sre_backend is not None:
            self._update_img_alt_text(img_elements)

        for img in img_elements:
            if not img.get("role"):
                img.set("role", "math")

        # --- <math> elements (already converted) --------------------------------
        for math_el in document.xpath('//*[local-name()="math"]'):
            if not math_el.get("role"):
                math_el.set("role", "math")

    def _update_img_alt_text(self, img_elements: list) -> None:
        """Replace LaTeX ``alt`` with spoken text; preserve LaTeX in ``data-latex``.

        Uses the SRE backend to convert each LaTeX expression to a
        plain-English spoken description.  If the batch conversion fails the
        ``alt`` attributes are left unchanged and a warning is logged.
        """
        from .math.backends.sre_backend import SpeechConversionError
        from .math.detector import _is_display

        items = []
        for img in img_elements:
            latex = (img.get("alt") or "").strip()
            items.append((latex, _is_display(img)))

        try:
            speeches = self._sre_backend.to_speech_batch(items)
        except SpeechConversionError as exc:
            logger.warning(
                "prince-preprocess: SRE batch conversion failed, alt text not updated: %s",
                exc,
            )
            return

        for img, (latex, _display), speech in zip(img_elements, items, speeches):
            if not latex:
                continue
            # Preserve original LaTeX so downstream MathML detection still works.
            if not img.get("data-latex"):
                img.set("data-latex", latex)
            if speech:
                img.set("alt", speech)
