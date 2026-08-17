"""Post-process a tagged PDF to inject MathML as Associated Files on math tags.

When LuaLaTeX's ``luamml`` module does not embed MathML automatically (or is
not available), this module provides a fallback: it opens the generated PDF,
walks the structure tree to find math structure elements, and attaches the
corresponding MathML strings as Associated Files (AF) with
``/AFRelationship /Supplement``.

Two pipelines are supported:

* **MathML-substitution pipeline** — ``<img class="latex">`` elements were
  replaced with ``<math>`` elements before Prince ran.  Prince tags these as
  ``Formula`` structure elements.  Use :func:`inject_mathml_into_pdf`.

* **Gentle / image-only pipeline** — ``<img class="latex">`` elements are
  kept intact so Prince's visual rendering is pixel-perfect.  Prince tags
  each image as a ``Figure`` structure element.  Use
  :func:`inject_mathml_into_figures` together with
  :func:`extract_mathml_from_latex_images` to generate the MathML purely for
  accessibility attachment without touching the visual output.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from lxml import etree, html

logger = logging.getLogger(__name__)


def extract_mathml_from_html(processed_html: str) -> list[str]:
    """Extract serialised MathML strings from processed HTML.

    Returns one MathML string per ``<math>`` element, in document order.
    Each string is a well-formed ``<math …>…</math>`` fragment encoded as
    UTF-8 XML.
    """
    doc = html.document_fromstring(processed_html)
    math_elements = doc.xpath('//*[local-name()="math"]')
    results: list[str] = []
    for el in math_elements:
        # Ensure the math namespace is present
        if el.nsmap.get(None) is None and not el.get("xmlns"):
            el.set("xmlns", "http://www.w3.org/1998/Math/MathML")
        mathml_bytes = etree.tostring(el, encoding="unicode", pretty_print=True)
        results.append(mathml_bytes)
    return results


def extract_mathml_from_latex_images(
    processed_html: str,
    backend: Any | None = None,
) -> list[str]:
    """Convert LaTeX from ``<img class="latex">`` elements to MathML strings.

    Used by the gentle / image-only pipeline where math images are kept
    intact for visual fidelity.  The MathML is generated purely for
    accessibility attachment (as Associated Files on ``Figure`` structure
    elements in the PDF) and does not modify the HTML output.

    Parameters
    ----------
    processed_html:
        HTML string produced by the gentle pipeline — still contains
        ``<img class="latex">`` placeholders with LaTeX in ``alt`` or
        ``data-latex`` attributes.
    backend:
        A :class:`~pressbooks_export.math.backends.base.MathBackend`
        instance.  Defaults to
        :class:`~pressbooks_export.math.backends.mathjax_backend.MathJaxNodeBackend`
        when *None*.

    Returns
    -------
    list[str]
        One MathML string per equation image, in document order.  Equations
        that fail to convert are represented by an empty string so that the
        list length always matches the number of images (preserving
        positional alignment with PDF Figure elements).
    """
    from ..math.backends.base import MathConversionError
    from ..math.detector import find_latex_images

    if backend is None:
        from ..math.backends.mathjax_backend import MathJaxNodeBackend
        backend = MathJaxNodeBackend()

    doc = html.document_fromstring(processed_html.encode("utf-8"))
    latex_images = find_latex_images(doc)

    if not latex_images:
        return []

    results: list[str] = []

    # Prefer batch conversion when available (single Node.js subprocess).
    convert_batch = getattr(backend, "convert_batch", None)
    if callable(convert_batch):
        items = [(img.latex, img.display) for img in latex_images]
        try:
            batch: list[str | MathConversionError] = convert_batch(items)
        except MathConversionError as exc:
            logger.warning("MathML batch conversion failed: %s; falling back per-equation.", exc)
            batch = []

        if len(batch) == len(latex_images):
            for img, result in zip(latex_images, batch):
                if isinstance(result, MathConversionError):
                    logger.warning("MathML conversion failed for %r: %s", img.latex[:40], result)
                    results.append("")
                else:
                    results.append(_ensure_mathml_ns(result))
            return results
        # Fall through to per-equation path on unexpected batch length.

    for img in latex_images:
        try:
            mathml = backend.convert(img.latex, display=img.display)
            results.append(_ensure_mathml_ns(mathml))
        except MathConversionError as exc:
            logger.warning("MathML conversion failed for %r: %s", img.latex[:40], exc)
            results.append("")

    return results


def _ensure_mathml_ns(mathml: str) -> str:
    """Ensure the MathML namespace is declared on the root ``<math>`` element.

    Parses *mathml* with the XML parser (not the HTML parser) so that
    namespace declarations are handled correctly, then re-serialises.
    """
    el = etree.fromstring(mathml.encode("utf-8"))
    # If the MathML namespace is not already in the element's namespace map,
    # add it as the default namespace by rebuilding with a namespace-aware tag.
    if el.nsmap.get(None) is None:
        # Move the element into the MathML namespace by cloning with nsmap.
        ns = "http://www.w3.org/1998/Math/MathML"
        new_el = etree.Element(
            f"{{{ns}}}math",
            attrib={k: v for k, v in el.attrib.items()},
            nsmap={None: ns},
        )
        new_el[:] = el[:]
        new_el.text = el.text
        el = new_el
    return etree.tostring(el, encoding="unicode", pretty_print=True)


def _walk_struct_children(node: Any) -> list[Any]:
    """Recursively collect all structure element dictionaries from *node*."""
    import pikepdf

    results: list[Any] = []
    if isinstance(node, pikepdf.Array):
        for child in node:
            results.extend(_walk_struct_children(child))
    elif isinstance(node, pikepdf.Dictionary):
        results.append(node)
        if "/K" in node:
            results.extend(_walk_struct_children(node["/K"]))
    return results


def _find_struct_elements(pdf: Any, struct_tag: str) -> list[Any]:
    """Return all structure element dictionaries matching *struct_tag* in *pdf*.

    Parameters
    ----------
    pdf:
        An open :class:`pikepdf.Pdf` instance.
    struct_tag:
        The PDF structure type to match exactly, e.g. ``"Formula"`` or
        ``"Figure"``.  The leading ``/`` that pikepdf includes in the string
        representation of PDF Name objects is stripped before comparison so
        that ``"Formula"`` matches ``/Formula`` but not ``/MathFormula``.
    """
    root = pdf.Root
    if "/StructTreeRoot" not in root:
        return []
    struct_root = root["/StructTreeRoot"]
    if "/K" not in struct_root:
        return []
    all_nodes = _walk_struct_children(struct_root["/K"])
    return [
        node for node in all_nodes
        if "/S" in node and str(node["/S"]).lstrip("/") == struct_tag
    ]


def _find_formula_elements(pdf: Any) -> list[Any]:
    """Return all Formula structure element dictionaries in *pdf*."""
    return _find_struct_elements(pdf, "Formula")


def _struct_elem_has_mathml_af(elem: Any) -> bool:
    """Return True if *elem* already has an Associated File containing MathML."""
    import pikepdf

    if "/AF" not in elem:
        return False
    af = elem["/AF"]
    # AF can be a single filespec or an array of filespecs
    if isinstance(af, pikepdf.Array):
        specs = list(af)
    else:
        specs = [af]
    for spec in specs:
        if isinstance(spec, pikepdf.Dictionary):
            desc = str(spec.get("/Desc", ""))
            uf = str(spec.get("/UF", ""))
            if "mathml" in desc.lower() or "mathml" in uf.lower():
                return True
            # Also check embedded file subtype
            if "/EF" in spec:
                ef = spec["/EF"]
                for key in ("/F", "/UF"):
                    if key in ef:
                        stream = ef[key]
                        if isinstance(stream, pikepdf.Stream):
                            subtype = str(stream.get("/Subtype", ""))
                            if "mathml" in subtype.lower() or "xml" in subtype.lower():
                                return True
    return False


# Keep the old name as an alias so existing callers compile without change.
_formula_has_mathml_af = _struct_elem_has_mathml_af


def _inject_mathml_into_struct_elements(
    pdf_path: Path,
    mathml_strings: list[str],
    struct_tag: str,
    output_path: Path | None,
) -> int:
    """Core injection logic shared by the Formula and Figure pipelines."""
    import pikepdf

    if output_path is None:
        output_path = pdf_path

    pdf = pikepdf.open(pdf_path, allow_overwriting_input=True)

    elements = _find_struct_elements(pdf, struct_tag)
    if not elements:
        logger.warning(
            "No %s structure elements found in %s. "
            "The PDF may not be tagged or may not contain math.",
            struct_tag,
            pdf_path,
        )
        pdf.close()
        return 0

    updated = 0
    for i, elem in enumerate(elements):
        if i >= len(mathml_strings):
            logger.warning(
                "More %s elements (%d) than MathML strings (%d); "
                "remaining elements will not have MathML AFs.",
                struct_tag,
                len(elements),
                len(mathml_strings),
            )
            break

        mathml = mathml_strings[i]
        if not mathml:
            logger.debug("%s %d: empty MathML string, skipping.", struct_tag, i)
            continue

        # Skip if already has a MathML AF (e.g. from luamml or a previous run).
        if _struct_elem_has_mathml_af(elem):
            logger.debug("%s %d already has MathML AF, skipping.", struct_tag, i)
            continue

        mathml_bytes = mathml.encode("utf-8")

        # Create an embedded file stream.
        mathml_stream = pikepdf.Stream(pdf, mathml_bytes)
        mathml_stream["/Subtype"] = pikepdf.Name("/application/mathml+xml")

        # Create the file specification dictionary.
        filespec = pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name.Filespec,
                "/F": f"formula-{i}.mathml",
                "/UF": f"formula-{i}.mathml",
                "/Desc": f"MathML for formula {i}",
                "/AFRelationship": pikepdf.Name.Supplement,
                "/EF": pikepdf.Dictionary(
                    {
                        "/F": mathml_stream,
                        "/UF": mathml_stream,
                    }
                ),
            }
        )

        # Attach the filespec to the structure element.
        if "/AF" in elem:
            existing_af = elem["/AF"]
            if isinstance(existing_af, pikepdf.Array):
                existing_af.append(pdf.make_indirect(filespec))
            else:
                elem["/AF"] = pikepdf.Array(
                    [existing_af, pdf.make_indirect(filespec)]
                )
        else:
            elem["/AF"] = pikepdf.Array([pdf.make_indirect(filespec)])

        updated += 1

    if updated > 0:
        pdf.save(output_path)
        logger.info(
            "Injected MathML AFs into %d %s element(s) in %s.",
            updated,
            struct_tag,
            output_path,
        )
    else:
        logger.info("No %s elements needed MathML injection.", struct_tag)
        if output_path != pdf_path:
            import shutil
            shutil.copy2(pdf_path, output_path)

    pdf.close()
    return updated


def inject_mathml_into_pdf(
    pdf_path: Path,
    mathml_strings: list[str],
    output_path: Path | None = None,
) -> int:
    """Attach MathML Associated Files to Formula structure elements in a PDF.

    Used by the **MathML-substitution pipeline** where ``<img class="latex">``
    elements were replaced with ``<math>`` before Prince ran, so Prince tagged
    them as ``Formula`` structure elements.

    Parameters
    ----------
    pdf_path:
        Path to the tagged PDF to post-process.
    mathml_strings:
        List of MathML strings (one per formula, in document order) to
        attach to the corresponding Formula structure elements.
    output_path:
        Where to write the modified PDF.  Defaults to overwriting
        *pdf_path* in place.

    Returns
    -------
    int
        Number of Formula elements that were updated with MathML AFs.
    """
    return _inject_mathml_into_struct_elements(
        pdf_path, mathml_strings, "Formula", output_path
    )


def inject_mathml_into_figures(
    pdf_path: Path,
    mathml_strings: list[str],
    output_path: Path | None = None,
) -> int:
    """Attach MathML Associated Files to Figure structure elements in a PDF.

    Used by the **gentle / image-only pipeline** where ``<img class="latex">``
    elements are kept intact so Prince's visual rendering is unchanged.
    Because Prince sees images rather than ``<math>`` elements, it produces
    ``Figure`` structure elements (not ``Formula``).  MathML generated from
    the original LaTeX is attached as Associated Files so that screen readers
    and other assistive tools can still access the mathematical content.

    Parameters
    ----------
    pdf_path:
        Path to the tagged PDF to post-process.
    mathml_strings:
        List of MathML strings (one per equation image, in document order).
        Empty strings are skipped.  Obtain these by calling
        :func:`extract_mathml_from_latex_images` on the processed HTML.
    output_path:
        Where to write the modified PDF.  Defaults to overwriting
        *pdf_path* in place.

    Returns
    -------
    int
        Number of Figure elements that were updated with MathML AFs.
    """
    return _inject_mathml_into_struct_elements(
        pdf_path, mathml_strings, "Figure", output_path
    )
