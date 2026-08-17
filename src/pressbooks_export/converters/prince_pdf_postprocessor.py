"""Post-process a Prince-generated PDF to address PDF/UA-2 blocker gaps.

Prince XML outputs PDF 1.7 by default and omits two XMP/viewer-preference
entries required for PDF/UA-2 compliance:

* **Gap 2** – ``ViewerPreferences/DisplayDocTitle`` must be ``true``
  (ISO 14289-2 §7.1).
* **Gap 3** – XMP metadata must declare ``pdfuaid:part = 2``
  (ISO 14289-2 §6.7.3).

Both can be injected into an existing PDF with pikepdf without rebuilding the
document from scratch.

Note on Gap 1 (PDF version)
----------------------------
PDF/UA-2 requires PDF 2.0 (ISO 32000-2).  After consulting the Prince 16
documentation, PDF/UA-2 is **not supported** by Prince XML — Prince does not
produce PDF 2.0 output and does not satisfy PDF/UA-2 requirements via
``--pdf-version=2``.  Alternative tooling is required for a fully compliant
PDF/UA-2 output.  The ``upgrade_pdf_version`` helper in this module sets
the PDF version header via pikepdf, which is a lightweight change suitable
only as a stopgap measure — it does not perform a structural upgrade to meet
all PDF 2.0 requirements.  A full compliance check with veraPDF is recommended
after any post-processing pipeline.

Usage::

    from pressbooks_export.converters.prince_pdf_postprocessor import (
        postprocess_for_pdfua2,
    )
    postprocess_for_pdfua2(Path("output.pdf"))
"""

from __future__ import annotations

import logging
from pathlib import Path

import pikepdf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# XMP template for pdfuaid:part = 2
# ---------------------------------------------------------------------------

# The XMP specification (ISO 16684-1) requires that an XMP packet embedded in
# a PDF begins with the UTF-8 BOM (U+FEFF, encoded as \xef\xbb\xbf) in the
# xpacket begin PI.  The three characters below are the individual Latin-1
# code points that, when encoded as UTF-8 and read by an XMP parser, produce
# the expected BOM sequence at the byte level.
# The id attribute ('W5M0MpCehiHzreSzNTczkc9d') is the standard Adobe-defined
# magic number required by the XMP specification; it has no semantic meaning
# and must appear verbatim in compliant XMP packets.
_PDFUA2_XMP_PACKET = """\
<?xpacket begin='\xef\xbb\xbf' id='W5M0MpCehiHzreSzNTczkc9d'?>
<x:xmpmeta xmlns:x='adobe:ns:meta/'>
  <rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>
    <rdf:Description rdf:about=''
        xmlns:pdfuaid='http://www.aiim.org/pdfua/ns/id/'>
      <pdfuaid:part>2</pdfuaid:part>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end='w'?>"""


def fix_display_doc_title(pdf: "pikepdf.Pdf") -> None:
    """Set ``ViewerPreferences/DisplayDocTitle = true`` in *pdf* (in-place).

    PDF/UA-2 (ISO 14289-2 §7.1) requires that the document title is displayed
    in the viewer title bar rather than the file name.  Prince does not emit
    this flag automatically.

    Parameters
    ----------
    pdf:
        An open :class:`pikepdf.Pdf` instance (mutated in-place).
    """
    if "/ViewerPreferences" not in pdf.Root:
        pdf.Root["/ViewerPreferences"] = pikepdf.Dictionary()
    pdf.Root["/ViewerPreferences"]["/DisplayDocTitle"] = True
    logger.debug("Set ViewerPreferences/DisplayDocTitle = true")


def inject_pdfua2_xmp(pdf: "pikepdf.Pdf") -> None:
    """Inject or merge a ``pdfuaid:part = 2`` declaration into *pdf*'s XMP stream.

    If the PDF already contains an ``/Metadata`` stream the new RDF block is
    appended inside the existing ``<rdf:RDF>`` element using lxml for robust
    XML manipulation.  Otherwise a minimal XMP packet is written as a new
    stream.

    Parameters
    ----------
    pdf:
        An open :class:`pikepdf.Pdf` instance (mutated in-place).
    """
    from lxml import etree

    _PDFUAID_NS = "http://www.aiim.org/pdfua/ns/id/"
    _RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

    if "/Metadata" in pdf.Root:
        existing_stream = pdf.Root["/Metadata"]
        existing_bytes = existing_stream.read_bytes()

        # Use lxml to detect and merge the pdfuaid namespace.
        try:
            # Strip the xpacket PI wrappers for XML parsing; we'll restore them.
            raw = existing_bytes.decode("utf-8", errors="replace")
            # Extract inner XML (between xpacket PIs if present)
            inner_start = raw.find("<x:xmpmeta")
            inner_end = raw.rfind("</x:xmpmeta>")
            if inner_start == -1 or inner_end == -1:
                raise ValueError("Could not locate xmpmeta element")
            inner_xml = raw[inner_start : inner_end + len("</x:xmpmeta>")]
            packet_prefix = raw[:inner_start]
            packet_suffix = raw[inner_end + len("</x:xmpmeta>"):]

            root = etree.fromstring(inner_xml.encode("utf-8"))

            # Check if pdfuaid is already declared in any rdf:Description.
            pdfuaid_elems = root.findall(
                f".//{{{_RDF_NS}}}Description/{{{_PDFUAID_NS}}}part"
            )
            if pdfuaid_elems:
                logger.debug("XMP already contains pdfuaid:part, skipping injection.")
                return

            # Find the rdf:RDF element and append a new rdf:Description.
            rdf_rdf = root.find(f"{{{_RDF_NS}}}RDF")
            if rdf_rdf is None:
                raise ValueError("No rdf:RDF element found in XMP")

            desc = etree.SubElement(
                rdf_rdf,
                f"{{{_RDF_NS}}}Description",
                attrib={f"{{{_RDF_NS}}}about": ""},
                nsmap={"pdfuaid": _PDFUAID_NS},
            )
            etree.SubElement(desc, f"{{{_PDFUAID_NS}}}part").text = "2"

            merged_inner = etree.tostring(root, encoding="unicode", pretty_print=True)
            merged = packet_prefix + merged_inner + packet_suffix
            new_stream = pikepdf.Stream(pdf, merged.encode("utf-8"))
            new_stream["/Type"] = pikepdf.Name("/Metadata")
            new_stream["/Subtype"] = pikepdf.Name("/XML")
            pdf.Root["/Metadata"] = new_stream
            logger.debug("Merged pdfuaid:part=2 into existing XMP metadata stream.")
            return

        except (ValueError, UnicodeDecodeError) as exc:
            logger.warning(
                "Could not parse existing XMP stream (%s); writing new packet.", exc
            )
        except Exception as exc:  # noqa: BLE001 — lxml may raise internal types
            logger.warning(
                "Unexpected error parsing XMP stream (%s); writing new packet.", exc
            )

    # No existing metadata, or parse failed — write a complete new XMP packet.
    new_stream = pikepdf.Stream(pdf, _PDFUA2_XMP_PACKET.encode("utf-8"))
    new_stream["/Type"] = pikepdf.Name("/Metadata")
    new_stream["/Subtype"] = pikepdf.Name("/XML")
    pdf.Root["/Metadata"] = new_stream
    logger.debug("Wrote new XMP metadata stream with pdfuaid:part=2.")


def postprocess_for_pdfua2(
    pdf_path: Path,
    output_path: Path | None = None,
) -> None:
    """Apply all PDF/UA-2 post-processing fixes to a Prince-generated PDF.

    Applies:

    * :func:`fix_display_doc_title` — ``ViewerPreferences/DisplayDocTitle``
    * :func:`inject_pdfua2_xmp` — ``pdfuaid:part = 2`` XMP declaration

    Parameters
    ----------
    pdf_path:
        Path to the input PDF (typically the direct output of Prince XML).
    output_path:
        Where to write the modified PDF.  Defaults to overwriting *pdf_path*
        in place.
    """
    if output_path is None:
        output_path = pdf_path

    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        fix_display_doc_title(pdf)
        inject_pdfua2_xmp(pdf)
        pdf.save(output_path)

    logger.info("PDF/UA-2 post-processing complete: %s", output_path)
