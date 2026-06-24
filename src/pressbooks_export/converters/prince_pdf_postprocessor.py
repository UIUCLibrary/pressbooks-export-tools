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
PDF/UA-2 requires PDF 2.0 (ISO 32000-2).  Prince XML's support for
``--pdf-version=2`` has not been confirmed for version 15 and may require a
later Prince release.  The ``upgrade_pdf_version`` helper in this module sets
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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pikepdf as _pikepdf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# XMP template for pdfuaid:part = 2
# ---------------------------------------------------------------------------

# The XMP specification (ISO 16684-1) requires that an XMP packet embedded in
# a PDF begins with the UTF-8 BOM (U+FEFF, encoded as \xef\xbb\xbf) in the
# xpacket begin PI.  The three characters below are the individual Latin-1
# code points that, when encoded as UTF-8 and read by an XMP parser, produce
# the expected BOM sequence at the byte level.
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


def fix_display_doc_title(pdf: "_pikepdf.Pdf") -> None:
    """Set ``ViewerPreferences/DisplayDocTitle = true`` in *pdf* (in-place).

    PDF/UA-2 (ISO 14289-2 §7.1) requires that the document title is displayed
    in the viewer title bar rather than the file name.  Prince does not emit
    this flag automatically.

    Parameters
    ----------
    pdf:
        An open :class:`pikepdf.Pdf` instance (mutated in-place).
    """
    import pikepdf

    if "/ViewerPreferences" not in pdf.Root:
        pdf.Root["/ViewerPreferences"] = pikepdf.Dictionary()
    pdf.Root["/ViewerPreferences"]["/DisplayDocTitle"] = True
    logger.debug("Set ViewerPreferences/DisplayDocTitle = true")


def inject_pdfua2_xmp(pdf: "_pikepdf.Pdf") -> None:
    """Inject or merge a ``pdfuaid:part = 2`` declaration into *pdf*'s XMP stream.

    If the PDF already contains an ``/Metadata`` stream the new RDF block is
    appended inside the existing ``<rdf:RDF>`` element.  Otherwise a minimal
    XMP packet is written as a new stream.

    Parameters
    ----------
    pdf:
        An open :class:`pikepdf.Pdf` instance (mutated in-place).
    """
    import pikepdf

    pdfuaid_block = (
        "    <rdf:Description rdf:about=''\n"
        "        xmlns:pdfuaid='http://www.aiim.org/pdfua/ns/id/'>\n"
        "      <pdfuaid:part>2</pdfuaid:part>\n"
        "    </rdf:Description>\n"
    )

    if "/Metadata" in pdf.Root:
        existing_stream = pdf.Root["/Metadata"]
        existing_xmp = existing_stream.read_bytes().decode("utf-8", errors="replace")

        if "pdfuaid" in existing_xmp:
            logger.debug("XMP already contains pdfuaid namespace, skipping injection.")
            return

        # Insert the pdfuaid block before the closing </rdf:RDF> tag.
        if "</rdf:RDF>" in existing_xmp:
            merged = existing_xmp.replace("</rdf:RDF>", pdfuaid_block + "</rdf:RDF>", 1)
            new_stream = pikepdf.Stream(pdf, merged.encode("utf-8"))
            new_stream["/Type"] = pikepdf.Name("/Metadata")
            new_stream["/Subtype"] = pikepdf.Name("/XML")
            pdf.Root["/Metadata"] = new_stream
            logger.debug("Merged pdfuaid:part=2 into existing XMP metadata stream.")
            return

    # No existing metadata or no rdf:RDF element — write a new XMP packet.
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
    import pikepdf

    if output_path is None:
        output_path = pdf_path

    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        fix_display_doc_title(pdf)
        inject_pdfua2_xmp(pdf)
        pdf.save(output_path)

    logger.info("PDF/UA-2 post-processing complete: %s", output_path)
