"""Post-process a tagged PDF to inject MathML as Associated Files on Formula tags.

When LuaLaTeX's ``luamml`` module does not embed MathML automatically (or is
not available), this module provides a fallback: it opens the generated PDF,
walks the structure tree to find ``Formula`` elements, and attaches the
corresponding MathML strings as Associated Files (AF) with
``/AFRelationship /Supplement``.

This ensures that each ``<Formula>`` structure element in the tagged PDF has
a ``<math>`` Associated File — the key accessibility requirement for
PDF/UA-2 math content.
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


def _find_formula_elements(pdf: Any) -> list[Any]:
    """Return all Formula structure element dictionaries in *pdf*."""
    root = pdf.Root
    if "/StructTreeRoot" not in root:
        return []
    struct_root = root["/StructTreeRoot"]
    if "/K" not in struct_root:
        return []
    all_nodes = _walk_struct_children(struct_root["/K"])
    formulas = []
    for node in all_nodes:
        if "/S" in node:
            tag = str(node["/S"])
            if "Formula" in tag:
                formulas.append(node)
    return formulas


def _formula_has_mathml_af(formula: Any) -> bool:
    """Return True if *formula* already has an AF containing MathML."""
    import pikepdf

    if "/AF" not in formula:
        return False
    af = formula["/AF"]
    # AF can be a single filespec or an array of filespecs
    if isinstance(af, pikepdf.Array):
        specs = list(af)
    else:
        specs = [af]
    for spec in specs:
        if isinstance(spec, pikepdf.Dictionary):
            # Check MIME type
            mime = str(spec.get("/AFRelationship", ""))
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


def inject_mathml_into_pdf(
    pdf_path: Path,
    mathml_strings: list[str],
    output_path: Path | None = None,
) -> int:
    """Attach MathML Associated Files to Formula structure elements in a PDF.

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
    import pikepdf

    if output_path is None:
        output_path = pdf_path

    pdf = pikepdf.open(pdf_path, allow_overwriting_input=True)

    formulas = _find_formula_elements(pdf)
    if not formulas:
        logger.warning(
            "No Formula structure elements found in %s. "
            "The PDF may not be tagged or may not contain math.",
            pdf_path,
        )
        pdf.close()
        return 0

    updated = 0
    for i, formula in enumerate(formulas):
        if i >= len(mathml_strings):
            logger.warning(
                "More Formula elements (%d) than MathML strings (%d); "
                "remaining formulas will not have MathML AFs.",
                len(formulas),
                len(mathml_strings),
            )
            break

        # Skip if formula already has a MathML AF (e.g. from luamml)
        if _formula_has_mathml_af(formula):
            logger.debug("Formula %d already has MathML AF, skipping.", i)
            continue

        mathml = mathml_strings[i]
        mathml_bytes = mathml.encode("utf-8")

        # Create an embedded file stream
        mathml_stream = pikepdf.Stream(pdf, mathml_bytes)
        mathml_stream["/Subtype"] = pikepdf.Name("/application/mathml+xml")

        # Create the file specification dictionary
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

        # Attach the filespec to the Formula structure element
        if "/AF" in formula:
            existing_af = formula["/AF"]
            if isinstance(existing_af, pikepdf.Array):
                existing_af.append(pdf.make_indirect(filespec))
            else:
                formula["/AF"] = pikepdf.Array(
                    [existing_af, pdf.make_indirect(filespec)]
                )
        else:
            formula["/AF"] = pikepdf.Array([pdf.make_indirect(filespec)])

        updated += 1

    if updated > 0:
        pdf.save(output_path)
        logger.info(
            "Injected MathML AFs into %d Formula element(s) in %s.",
            updated,
            output_path,
        )
    else:
        logger.info("No Formula elements needed MathML injection.")
        if output_path != pdf_path:
            import shutil
            shutil.copy2(pdf_path, output_path)

    pdf.close()
    return updated
