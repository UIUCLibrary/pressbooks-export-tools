"""Tests for latex_extractor — HTML parsing, CSV writing, and SRE wiring."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pressbooks_export.latex_extractor import (
    LatexEntry,
    _find_latex_images,
    extract_latex,
    write_csv,
)
from pressbooks_export.math.backends.sre_backend import SpeechConversionError
from lxml import html


FIXTURE = Path(__file__).parent / "fixtures" / "sample_pressbooks_webbook.html"


# ---------------------------------------------------------------------------
# _find_latex_images
# ---------------------------------------------------------------------------


def test_find_latex_images_default_classes_matches_both_classes() -> None:
    markup = FIXTURE.read_text(encoding="utf-8")
    document = html.fromstring(markup)
    results = _find_latex_images(document, ["latex", "mathjax"])
    # Only the two imgs that have BOTH "latex" and "mathjax" and a non-empty alt
    assert [r[0] for r in results] == [
        "x^2 + y^2 = z^2",
        r"\frac{-b \pm \sqrt{b^2 - 4ac}}{2a}",
    ]


def test_find_latex_images_display_flag() -> None:
    markup = FIXTURE.read_text(encoding="utf-8")
    document = html.fromstring(markup)
    results = _find_latex_images(document, ["latex", "mathjax"])
    assert results[0][1] is False   # inline
    assert results[1][1] is True    # block


def test_find_latex_images_single_class_filter() -> None:
    markup = FIXTURE.read_text(encoding="utf-8")
    document = html.fromstring(markup)
    # With only "latex" we should pick up the third img too
    results = _find_latex_images(document, ["latex"])
    latexes = [r[0] for r in results]
    assert r"\alpha + \beta" in latexes


def test_find_latex_images_skips_missing_alt() -> None:
    markup = '<html><body><img class="latex mathjax" src="x.png" /></body></html>'
    document = html.fromstring(markup)
    results = _find_latex_images(document, ["latex", "mathjax"])
    assert results == []


# ---------------------------------------------------------------------------
# extract_latex — with a stubbed SRE backend
# ---------------------------------------------------------------------------


def _make_stub_backend(speech_map: dict[str, str] | None = None) -> MagicMock:
    """Return a MagicMock SreNodeBackend whose to_speech follows *speech_map*."""
    backend = MagicMock()
    speech_map = speech_map or {}
    backend.to_speech.side_effect = lambda latex, display=False: speech_map.get(
        latex, f"spoken: {latex}"
    )
    return backend


def test_extract_latex_returns_entries_with_speech() -> None:
    html_content = FIXTURE.read_text(encoding="utf-8")
    backend = _make_stub_backend({"x^2 + y^2 = z^2": "x squared plus y squared equals z squared"})

    entries = extract_latex(html_content, sre_backend=backend)

    assert len(entries) == 2
    assert entries[0].latex == "x^2 + y^2 = z^2"
    assert entries[0].display is False
    assert entries[0].speech == "x squared plus y squared equals z squared"
    assert entries[1].display is True


def test_extract_latex_defaults_to_latex_mathjax_classes() -> None:
    html_content = FIXTURE.read_text(encoding="utf-8")
    backend = _make_stub_backend()
    entries = extract_latex(html_content, sre_backend=backend)
    # The img with only class="latex" (no mathjax) should be excluded
    latexes = [e.latex for e in entries]
    assert r"\alpha + \beta" not in latexes


def test_extract_latex_custom_classes() -> None:
    html_content = FIXTURE.read_text(encoding="utf-8")
    backend = _make_stub_backend()
    entries = extract_latex(html_content, classes=["latex"], sre_backend=backend)
    latexes = [e.latex for e in entries]
    assert r"\alpha + \beta" in latexes


def test_extract_latex_sre_failure_produces_empty_speech(caplog: pytest.LogCaptureFixture) -> None:
    """A SpeechConversionError is logged as a warning; speech is left empty."""
    html_content = '<html><body><img class="latex mathjax" alt="x" /></body></html>'
    backend = MagicMock()
    backend.to_speech.side_effect = SpeechConversionError("node not found")

    import logging
    with caplog.at_level(logging.WARNING, logger="pressbooks_export.latex_extractor"):
        entries = extract_latex(html_content, sre_backend=backend)

    assert entries[0].speech == ""
    assert "node not found" in caplog.text


# ---------------------------------------------------------------------------
# write_csv
# ---------------------------------------------------------------------------


def test_write_csv_produces_correct_columns(tmp_path: Path) -> None:
    entries = [
        LatexEntry(latex="x^2", display=False, speech="x squared"),
        LatexEntry(latex=r"\frac{1}{2}", display=True, speech="one half"),
    ]
    out = tmp_path / "out.csv"
    write_csv(entries, out)

    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert rows[0] == {"latex": "x^2", "display": "inline", "speech": "x squared"}
    assert rows[1] == {"latex": r"\frac{1}{2}", "display": "block", "speech": "one half"}


def test_write_csv_creates_parent_dirs(tmp_path: Path) -> None:
    out = tmp_path / "sub" / "dir" / "out.csv"
    write_csv([], out)
    assert out.exists()


def test_write_csv_header_row(tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    write_csv([], out)
    content = out.read_text(encoding="utf-8")
    assert content.startswith("latex,display,speech")
