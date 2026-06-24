"""Tests for prince_pdf_postprocessor."""
from __future__ import annotations

import pytest

pikepdf = pytest.importorskip("pikepdf")

from pressbooks_export.converters.prince_pdf_postprocessor import (
    fix_display_doc_title,
    inject_pdfua2_xmp,
    postprocess_for_pdfua2,
)


def _make_minimal_pdf() -> "pikepdf.Pdf":
    """Return a minimal in-memory PDF for testing."""
    pdf = pikepdf.new()
    page = pikepdf.Page(pikepdf.Dictionary(
        Type=pikepdf.Name.Page,
        MediaBox=pikepdf.Array([0, 0, 612, 792]),
    ))
    pdf.pages.append(page)
    return pdf


# ---------------------------------------------------------------------------
# fix_display_doc_title
# ---------------------------------------------------------------------------

def test_fix_display_doc_title_sets_flag() -> None:
    pdf = _make_minimal_pdf()
    fix_display_doc_title(pdf)
    assert pdf.Root["/ViewerPreferences"]["/DisplayDocTitle"] == True


def test_fix_display_doc_title_creates_viewer_prefs_if_absent() -> None:
    pdf = _make_minimal_pdf()
    assert "/ViewerPreferences" not in pdf.Root
    fix_display_doc_title(pdf)
    assert "/ViewerPreferences" in pdf.Root


def test_fix_display_doc_title_preserves_existing_prefs() -> None:
    pdf = _make_minimal_pdf()
    pdf.Root["/ViewerPreferences"] = pikepdf.Dictionary(
        HideMenubar=True,
    )
    fix_display_doc_title(pdf)
    assert pdf.Root["/ViewerPreferences"]["/DisplayDocTitle"] == True
    assert pdf.Root["/ViewerPreferences"]["/HideMenubar"] == True


# ---------------------------------------------------------------------------
# inject_pdfua2_xmp
# ---------------------------------------------------------------------------

def test_inject_pdfua2_xmp_creates_metadata_stream() -> None:
    pdf = _make_minimal_pdf()
    inject_pdfua2_xmp(pdf)
    assert "/Metadata" in pdf.Root
    xmp = pdf.Root["/Metadata"].read_bytes().decode()
    assert "pdfuaid" in xmp
    assert "<pdfuaid:part>2</pdfuaid:part>" in xmp


def test_inject_pdfua2_xmp_does_not_duplicate_if_already_present() -> None:
    pdf = _make_minimal_pdf()
    inject_pdfua2_xmp(pdf)
    # Call again — should not raise or duplicate the declaration.
    inject_pdfua2_xmp(pdf)
    xmp = pdf.Root["/Metadata"].read_bytes().decode()
    # "<pdfuaid:part>" (opening tag only) appears exactly once per declaration.
    assert xmp.count("<pdfuaid:part>") == 1


def test_inject_pdfua2_xmp_merges_into_existing_metadata() -> None:
    pdf = _make_minimal_pdf()
    existing_xmp = (
        "<?xpacket begin='' id='test'?>"
        "<x:xmpmeta xmlns:x='adobe:ns:meta/'>"
        "<rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>"
        "<rdf:Description rdf:about='' xmlns:dc='http://purl.org/dc/elements/1.1/'>"
        "<dc:title>My Book</dc:title>"
        "</rdf:Description>"
        "</rdf:RDF>"
        "</x:xmpmeta>"
        "<?xpacket end='w'?>"
    )
    stream = pikepdf.Stream(pdf, existing_xmp.encode())
    stream["/Type"] = pikepdf.Name("/Metadata")
    stream["/Subtype"] = pikepdf.Name("/XML")
    pdf.Root["/Metadata"] = stream

    inject_pdfua2_xmp(pdf)

    xmp = pdf.Root["/Metadata"].read_bytes().decode()
    assert "dc:title" in xmp
    assert "<pdfuaid:part>2</pdfuaid:part>" in xmp


# ---------------------------------------------------------------------------
# postprocess_for_pdfua2 (round-trip file test)
# ---------------------------------------------------------------------------

def test_postprocess_for_pdfua2_round_trip(tmp_path: "pathlib.Path") -> None:
    import pathlib
    pdf = _make_minimal_pdf()
    pdf_path = tmp_path / "test.pdf"
    pdf.save(str(pdf_path))

    postprocess_for_pdfua2(pathlib.Path(pdf_path))

    with pikepdf.open(str(pdf_path)) as result:
        assert result.Root["/ViewerPreferences"]["/DisplayDocTitle"] == True
        xmp = result.Root["/Metadata"].read_bytes().decode()
        assert "<pdfuaid:part>2</pdfuaid:part>" in xmp


def test_postprocess_for_pdfua2_writes_to_output_path(tmp_path: "pathlib.Path") -> None:
    import pathlib
    pdf = _make_minimal_pdf()
    pdf_path = tmp_path / "input.pdf"
    out_path = tmp_path / "output.pdf"
    pdf.save(str(pdf_path))

    postprocess_for_pdfua2(pathlib.Path(pdf_path), pathlib.Path(out_path))

    assert out_path.exists()
    with pikepdf.open(str(out_path)) as result:
        assert "/Metadata" in result.Root
