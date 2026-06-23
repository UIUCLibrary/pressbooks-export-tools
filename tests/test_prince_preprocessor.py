"""Tests for PrinceHtmlPreprocessor."""
from __future__ import annotations

from lxml import html

from pressbooks_export.prince_preprocessor import PrinceHtmlPreprocessor


PREPROCESSOR = PrinceHtmlPreprocessor()


def _parse(markup: str) -> html.HtmlElement:
    return html.fromstring(markup)


# ---------------------------------------------------------------------------
# TOC landmark
# ---------------------------------------------------------------------------

def test_toc_gets_navigation_role() -> None:
    markup = '<html><body><div id="toc"><h1>Contents</h1><ul><li>Chapter 1</li></ul></div></body></html>'
    result = PREPROCESSOR.process_html(markup)
    doc = _parse(result)
    toc = doc.get_element_by_id("toc")
    assert toc.get("role") == "navigation"


def test_toc_gets_aria_label() -> None:
    markup = '<html><body><div id="toc"><ul></ul></div></body></html>'
    result = PREPROCESSOR.process_html(markup)
    doc = _parse(result)
    assert doc.get_element_by_id("toc").get("aria-label") == "Table of Contents"


def test_toc_existing_role_not_overwritten() -> None:
    markup = '<html><body><div id="toc" role="complementary"><ul></ul></div></body></html>'
    result = PREPROCESSOR.process_html(markup)
    doc = _parse(result)
    assert doc.get_element_by_id("toc").get("role") == "complementary"


# ---------------------------------------------------------------------------
# Copyright page
# ---------------------------------------------------------------------------

def test_copyright_page_gets_contentinfo_role() -> None:
    markup = '<html><body><div id="copyright-page"><p>Copyright</p></div></body></html>'
    result = PREPROCESSOR.process_html(markup)
    doc = _parse(result)
    elem = doc.get_element_by_id("copyright-page")
    assert elem.get("role") == "contentinfo"
    assert elem.get("aria-label") == "Copyright"


# ---------------------------------------------------------------------------
# Title page
# ---------------------------------------------------------------------------

def test_title_page_gets_region_role() -> None:
    markup = '<html><body><div id="title-page"><h1>My Book</h1></div></body></html>'
    result = PREPROCESSOR.process_html(markup)
    doc = _parse(result)
    elem = doc.get_element_by_id("title-page")
    assert elem.get("role") == "region"
    assert elem.get("aria-label") == "Title Page"


# ---------------------------------------------------------------------------
# Chapter / front-matter / back-matter sections
# ---------------------------------------------------------------------------

def test_chapter_div_gets_region_role_from_title() -> None:
    markup = (
        '<html><body>'
        '<div class="chapter standard" id="ch1" title="Introduction to Probability">'
        '<h1>Introduction to Probability</h1>'
        '</div>'
        '</body></html>'
    )
    result = PREPROCESSOR.process_html(markup)
    doc = _parse(result)
    elem = doc.get_element_by_id("ch1")
    assert elem.get("role") == "region"
    assert elem.get("aria-label") == "Introduction to Probability"


def test_front_matter_gets_aria_label() -> None:
    markup = (
        '<html><body>'
        '<div class="front-matter introduction" id="fm1" title="Preface">'
        '<h1>Preface</h1>'
        '</div>'
        '</body></html>'
    )
    result = PREPROCESSOR.process_html(markup)
    doc = _parse(result)
    elem = doc.get_element_by_id("fm1")
    assert elem.get("aria-label") == "Preface"


def test_section_without_title_not_labelled() -> None:
    """Sections without a title attribute should not receive aria-label."""
    markup = (
        '<html><body>'
        '<div class="chapter standard" id="ch-no-title">'
        '<h1>Chapter</h1>'
        '</div>'
        '</body></html>'
    )
    result = PREPROCESSOR.process_html(markup)
    doc = _parse(result)
    elem = doc.get_element_by_id("ch-no-title")
    assert elem.get("aria-label") is None
    assert elem.get("role") is None


def test_existing_aria_label_not_overwritten() -> None:
    markup = (
        '<html><body>'
        '<div class="chapter standard" id="ch2" title="New Title" aria-label="Custom Label">'
        '</div>'
        '</body></html>'
    )
    result = PREPROCESSOR.process_html(markup)
    doc = _parse(result)
    assert doc.get_element_by_id("ch2").get("aria-label") == "Custom Label"


# ---------------------------------------------------------------------------
# Part wrapper
# ---------------------------------------------------------------------------

def test_part_wrapper_labelled_from_heading() -> None:
    markup = (
        '<html><body>'
        '<div class="part-wrapper" id="part1">'
        '<h1>Part I: Foundations</h1>'
        '<div class="chapter standard" id="ch3" title="Chapter 1">'
        '<h1>Chapter 1</h1>'
        '</div>'
        '</div>'
        '</body></html>'
    )
    result = PREPROCESSOR.process_html(markup)
    doc = _parse(result)
    part = doc.get_element_by_id("part1")
    assert part.get("role") == "region"
    assert part.get("aria-label") == "Part I: Foundations"


# ---------------------------------------------------------------------------
# HTML lang attribute
# ---------------------------------------------------------------------------

def test_lang_attribute_added_from_xml_lang() -> None:
    markup = (
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xml:lang="en"><head></head><body><p>Hello</p></body></html>'
    )
    result = PREPROCESSOR.process_html(markup)
    doc = _parse(result)
    root = doc if doc.tag == "html" else doc.find(".//html")
    if root is not None:
        assert root.get("lang") == "en"


def test_existing_lang_not_overwritten() -> None:
    markup = '<html lang="fr" xml:lang="fr"><body><p>Bonjour</p></body></html>'
    result = PREPROCESSOR.process_html(markup)
    doc = _parse(result)
    root = doc if doc.tag == "html" else doc.find(".//html")
    if root is not None:
        assert root.get("lang") == "fr"
