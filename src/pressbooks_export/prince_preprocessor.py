"""HTML preprocessor that adds ARIA landmarks and roles to Pressbooks exports.

Pressbooks HTML exports lack the ARIA landmark roles (``navigation``,
``region``, ``contentinfo``, etc.) that Prince XML uses when building the
accessibility tag tree of a PDF.  This module supplies a thin preprocessing
step that inserts those attributes so that Prince can produce a more
accessible tagged PDF without requiring changes to Pressbooks itself.

Usage::

    from pressbooks_export.prince_preprocessor import PrinceHtmlPreprocessor
    preprocessor = PrinceHtmlPreprocessor()
    accessible_html = preprocessor.process_file(Path("export.html"))

A ticket has been opened with Pressbooks to add these attributes natively;
once that lands, this preprocessing step can be removed.
"""

from __future__ import annotations

from pathlib import Path

from lxml import html


# ---------------------------------------------------------------------------
# Landmark mapping for well-known Pressbooks div IDs
# ---------------------------------------------------------------------------

#: Mapping of ``<div id="...">`` values to (role, aria-label) pairs.
_ID_LANDMARK_MAP: dict[str, tuple[str, str]] = {
    "toc": ("navigation", "Table of Contents"),
    "title-page": ("region", "Title Page"),
    "half-title-page": ("region", "Half Title Page"),
    "copyright-page": ("contentinfo", "Copyright"),
}

#: CSS classes whose outermost ``<div>`` elements should become labelled
#: regions.  Order matters: the first matching class wins.
_SECTION_CLASSES: tuple[str, ...] = (
    "chapter",
    "front-matter",
    "back-matter",
    "appendix",
    "part-wrapper",
)


class PrinceHtmlPreprocessor:
    """Add ARIA landmark roles and labels to a Pressbooks HTML export.

    The preprocessor makes four categories of change:

    1. **Known IDs** – ``<div id="toc">``, ``<div id="copyright-page">``, etc.
       receive an explicit ``role`` and ``aria-label``.
    2. **Section divs** – ``<div class="chapter …">`` and similar Pressbooks
       section wrappers gain ``role="region"`` and an ``aria-label`` sourced
       from their existing ``title`` attribute.
    3. **Part wrappers** – ``<div class="part-wrapper">`` elements are treated
       as regions labelled after the first ``<h1>`` or ``<h2>`` they contain.
    4. **HTML ``lang`` attribute** – If the ``<html>`` element has only
       ``xml:lang`` (XHTML heritage) but no plain ``lang``, the plain ``lang``
       attribute is added so that Prince picks up the document language.
    """

    def process_html(self, markup: str) -> str:
        """Return *markup* with ARIA landmarks and roles injected."""
        document = html.fromstring(markup)
        self._fix_html_lang(document)
        self._add_id_landmarks(document)
        self._add_section_region_labels(document)
        self._add_part_wrapper_labels(document)
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

    @staticmethod
    def _add_id_landmarks(document: html.HtmlElement) -> None:
        """Add ``role`` / ``aria-label`` to ``<div>`` elements with known IDs."""
        for div_id, (role, label) in _ID_LANDMARK_MAP.items():
            elements = document.xpath(f'//div[@id="{div_id}"]')
            for elem in elements:
                if not elem.get("role"):
                    elem.set("role", role)
                if not elem.get("aria-label"):
                    elem.set("aria-label", label)

    @staticmethod
    def _add_section_region_labels(document: html.HtmlElement) -> None:
        """Add ``role="region"`` and ``aria-label`` to Pressbooks section wrappers.

        Pressbooks chapter / front-matter / back-matter ``<div>`` elements
        already carry a ``title`` attribute with a human-readable section
        name.  This method copies that value to ``aria-label`` and adds
        ``role="region"`` so Prince can create a named region structure
        element in the PDF tag tree.
        """
        for section_class in _SECTION_CLASSES:
            xpath = (
                f'//div[contains(concat(" ", normalize-space(@class), " "),'
                f' " {section_class} ")][@title]'
            )
            for elem in document.xpath(xpath):
                title = (elem.get("title") or "").strip()
                if not title:
                    continue
                if not elem.get("role"):
                    elem.set("role", "region")
                if not elem.get("aria-label"):
                    elem.set("aria-label", title)

    @staticmethod
    def _add_part_wrapper_labels(document: html.HtmlElement) -> None:
        """Label ``<div class="part-wrapper">`` elements without a ``title``.

        Part wrappers in Pressbooks exports do not always have a ``title``
        attribute, but they contain a heading element that can serve as the
        region label.
        """
        for elem in document.xpath('//div[contains(@class, "part-wrapper")]'):
            if elem.get("aria-label"):
                continue
            # Use the first heading inside the wrapper as the label.
            headings = elem.xpath(".//h1 | .//h2 | .//h3")
            heading = headings[0] if headings else None
            if heading is not None:
                label = (heading.text_content() or "").strip()
                if label:
                    if not elem.get("role"):
                        elem.set("role", "region")
                    elem.set("aria-label", label)
