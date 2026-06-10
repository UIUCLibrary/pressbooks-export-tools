from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from pressbooks_export.converters.base import OutputConversionError
from pressbooks_export.converters.pdf import PandocLuaLatexPdfConverter, _find_lualatex, _PANDOC_TEMPLATE


# --- _find_lualatex -----------------------------------------------------------


def test_find_lualatex_prefers_dev() -> None:
    """lualatex-dev should be returned when both binaries are on PATH."""
    with mock.patch("shutil.which", side_effect=lambda name: f"/usr/bin/{name}" if name in ("lualatex-dev", "lualatex") else None):
        assert _find_lualatex() == "/usr/bin/lualatex-dev"


def test_find_lualatex_falls_back_to_stable() -> None:
    """Falls back to lualatex when lualatex-dev is absent."""
    def _which(name: str) -> str | None:
        return "/usr/bin/lualatex" if name == "lualatex" else None

    with mock.patch("shutil.which", side_effect=_which):
        assert _find_lualatex() == "/usr/bin/lualatex"


def test_find_lualatex_raises_when_neither_found() -> None:
    with mock.patch("shutil.which", return_value=None):
        with pytest.raises(OutputConversionError, match="lualatex-dev"):
            _find_lualatex()


# --- Template existence -------------------------------------------------------


def test_ua2_template_exists() -> None:
    assert _PANDOC_TEMPLATE.exists(), f"Template not found at {_PANDOC_TEMPLATE}"


def test_ua2_template_has_document_metadata() -> None:
    content = _PANDOC_TEMPLATE.read_text(encoding="utf-8")
    assert r"\DocumentMetadata{" in content
    assert "pdfstandard=ua-2" in content
    assert "tagging=on" in content
    assert "testphase=math" in content


def test_ua2_template_has_document_metadata_before_documentclass() -> None:
    content = _PANDOC_TEMPLATE.read_text(encoding="utf-8")
    meta_pos = content.index(r"\DocumentMetadata{")
    # Find the actual \documentclass command (not mentions in comments)
    class_pos = content.index(r"\documentclass[")
    assert meta_pos < class_pos, (
        r"\DocumentMetadata must appear before \documentclass"
    )


# --- PandocLuaLatexPdfConverter ------------------------------------------------


def test_converter_passes_template_and_engine(tmp_path: Path) -> None:
    """Verify the converter passes --template and --pdf-engine flags to Pandoc."""
    captured_cmd: list[str] = []

    def fake_run(cmd: list[str], **kwargs):  # type: ignore[no-untyped-def]
        captured_cmd.extend(cmd)
        return mock.Mock(returncode=0, stderr="")

    with (
        mock.patch("shutil.which", side_effect=lambda n: f"/usr/bin/{n}" if n in ("pandoc", "lualatex-dev") else None),
        mock.patch("pressbooks_export.converters.pdf.subprocess.run", side_effect=fake_run),
    ):
        converter = PandocLuaLatexPdfConverter()
        converter.convert_html(tmp_path / "in.html", tmp_path / "out.pdf")

    cmd_str = " ".join(captured_cmd)
    assert "--pdf-engine=/usr/bin/lualatex-dev" in cmd_str
    assert f"--template={_PANDOC_TEMPLATE}" in cmd_str
