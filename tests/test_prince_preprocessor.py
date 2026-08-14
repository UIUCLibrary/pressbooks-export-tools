"""Tests for PrinceHtmlPreprocessor."""
from __future__ import annotations

import pytest
from lxml import html

from pressbooks_export.math.backends.sre_backend import SreNodeBackend
from pressbooks_export.prince_preprocessor import PrinceHtmlPreprocessor


def _parse(markup: str) -> html.HtmlElement:
    return html.fromstring(markup)


class StubSreBackend(SreNodeBackend):
    """SRE backend test double that returns predictable spoken descriptions."""

    def __init__(self) -> None:
        pass  # Skip Node.js path setup

    def to_speech_batch(self, items: list[tuple[str, bool]]) -> list[str]:
        return [f"spoken: {latex}" for latex, _display in items]


@pytest.fixture()
def preprocessor() -> PrinceHtmlPreprocessor:
    return PrinceHtmlPreprocessor()


@pytest.fixture()
def preprocessor_with_sre() -> PrinceHtmlPreprocessor:
    return PrinceHtmlPreprocessor(sre_backend=StubSreBackend())


# ---------------------------------------------------------------------------
# role="math" on <img class="latex"> elements
# ---------------------------------------------------------------------------

def test_latex_img_gets_math_role(preprocessor: PrinceHtmlPreprocessor) -> None:
    markup = '<html><body><p><img class="latex" alt="x^2" /></p></body></html>'
    result = preprocessor.process_html(markup)
    doc = _parse(result)
    img = doc.xpath('//img[contains(@class, "latex")]')[0]
    assert img.get("role") == "math"


def test_existing_role_not_overwritten_on_img(preprocessor: PrinceHtmlPreprocessor) -> None:
    markup = '<html><body><p><img class="latex" alt="x^2" role="img" /></p></body></html>'
    result = preprocessor.process_html(markup)
    doc = _parse(result)
    img = doc.xpath('//img[contains(@class, "latex")]')[0]
    assert img.get("role") == "img"


def test_img_without_alt_still_gets_role(preprocessor: PrinceHtmlPreprocessor) -> None:
    """An image with no alt text still receives role="math" as a markup-level annotation."""
    markup = '<html><body><p><img class="latex" /></p></body></html>'
    result = preprocessor.process_html(markup)
    doc = _parse(result)
    img = doc.xpath('//img[contains(@class, "latex")]')[0]
    # role="math" is added based on the class, independent of alt content.
    assert img.get("role") == "math"


# ---------------------------------------------------------------------------
# role="math" on <math> elements (already converted)
# ---------------------------------------------------------------------------

def test_math_element_gets_math_role(preprocessor: PrinceHtmlPreprocessor) -> None:
    markup = '<html><body><p><math><mtext>x+y</mtext></math></p></body></html>'
    result = preprocessor.process_html(markup)
    doc = _parse(result)
    math_el = doc.xpath('//*[local-name()="math"]')[0]
    assert math_el.get("role") == "math"


def test_existing_role_not_overwritten_on_math(preprocessor: PrinceHtmlPreprocessor) -> None:
    markup = '<html><body><p><math role="presentation"><mtext>x</mtext></math></p></body></html>'
    result = preprocessor.process_html(markup)
    doc = _parse(result)
    math_el = doc.xpath('//*[local-name()="math"]')[0]
    assert math_el.get("role") == "presentation"


# ---------------------------------------------------------------------------
# Spoken alt text update (with SRE backend)
# ---------------------------------------------------------------------------

def test_alt_updated_to_spoken_with_sre(preprocessor_with_sre: PrinceHtmlPreprocessor) -> None:
    markup = '<html><body><p><img class="latex" alt="x^2" /></p></body></html>'
    result = preprocessor_with_sre.process_html(markup)
    doc = _parse(result)
    img = doc.xpath('//img[contains(@class, "latex")]')[0]
    assert img.get("alt") == "spoken: x^2"


def test_original_latex_preserved_in_data_latex(preprocessor_with_sre: PrinceHtmlPreprocessor) -> None:
    markup = '<html><body><p><img class="latex" alt="\\frac{1}{2}" /></p></body></html>'
    result = preprocessor_with_sre.process_html(markup)
    doc = _parse(result)
    img = doc.xpath('//img[contains(@class, "latex")]')[0]
    assert img.get("data-latex") == "\\frac{1}{2}"
    assert img.get("alt") == "spoken: \\frac{1}{2}"


def test_alt_unchanged_without_sre(preprocessor: PrinceHtmlPreprocessor) -> None:
    markup = '<html><body><p><img class="latex" alt="x^2" /></p></body></html>'
    result = preprocessor.process_html(markup)
    doc = _parse(result)
    img = doc.xpath('//img[contains(@class, "latex")]')[0]
    assert img.get("alt") == "x^2"
    assert img.get("data-latex") is None


def test_existing_data_latex_not_overwritten(preprocessor_with_sre: PrinceHtmlPreprocessor) -> None:
    """If data-latex is already set, it should not be overwritten."""
    markup = (
        '<html><body>'
        '<p><img class="latex" alt="spoken already" data-latex="x^2" /></p>'
        '</body></html>'
    )
    result = preprocessor_with_sre.process_html(markup)
    doc = _parse(result)
    img = doc.xpath('//img[contains(@class, "latex")]')[0]
    # data-latex should not be overwritten
    assert img.get("data-latex") == "x^2"


def test_role_added_even_with_sre(preprocessor_with_sre: PrinceHtmlPreprocessor) -> None:
    markup = '<html><body><p><img class="latex" alt="x^2" /></p></body></html>'
    result = preprocessor_with_sre.process_html(markup)
    doc = _parse(result)
    img = doc.xpath('//img[contains(@class, "latex")]')[0]
    assert img.get("role") == "math"


# ---------------------------------------------------------------------------
# HTML lang attribute
# ---------------------------------------------------------------------------

def test_lang_attribute_added_from_xml_lang(preprocessor: PrinceHtmlPreprocessor) -> None:
    markup = (
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xml:lang="en"><head></head><body><p>Hello</p></body></html>'
    )
    result = preprocessor.process_html(markup)
    doc = _parse(result)
    root = doc if doc.tag == "html" else doc.find(".//html")
    if root is not None:
        assert root.get("lang") == "en"


def test_existing_lang_not_overwritten(preprocessor: PrinceHtmlPreprocessor) -> None:
    markup = '<html lang="fr" xml:lang="fr"><body><p>Bonjour</p></body></html>'
    result = preprocessor.process_html(markup)
    doc = _parse(result)
    root = doc if doc.tag == "html" else doc.find(".//html")
    if root is not None:
        assert root.get("lang") == "fr"



# ---------------------------------------------------------------------------
# MathML fixes for Prince XML (accent=true on mover, stretchy=false on OP mo)
# ---------------------------------------------------------------------------

def test_preprocessor_adds_accent_true_to_mover(preprocessor: PrinceHtmlPreprocessor) -> None:
    """PrinceHtmlPreprocessor must add accent='true' to <mover> whose accent mo has stretchy='false'.

    This covers the MathJax pipeline where clean.html already contains <math>
    elements: the preprocessor must fix them even though no <img> conversion
    takes place at this stage.
    """
    _MML = "http://www.w3.org/1998/Math/MathML"
    markup = (
        '<html><body>'
        f'<math xmlns="{_MML}">'
        '<mrow data-mjx-texclass="ORD">'
        '<mover><mi>x</mi><mo stretchy="false">&#xAF;</mo></mover>'
        '</mrow>'
        '</math>'
        '</body></html>'
    )
    result = preprocessor.process_html(markup)
    assert 'accent="true"' in result, (
        "PrinceHtmlPreprocessor must add accent='true' to <mover> for x-bar to render correctly"
    )


def test_preprocessor_adds_stretchy_false_to_op_mo(preprocessor: PrinceHtmlPreprocessor) -> None:
    """PrinceHtmlPreprocessor must add stretchy='false' to <mo data-mjx-texclass='OP'>.

    Without this, Prince expands sigma (∑) as a large stretchy operator.
    """
    _MML = "http://www.w3.org/1998/Math/MathML"
    markup = (
        '<html><body>'
        f'<math xmlns="{_MML}">'
        '<mo data-mjx-texclass="OP">&#x2211;</mo>'
        '</math>'
        '</body></html>'
    )
    result = preprocessor.process_html(markup)
    # The mo element should now carry stretchy="false"
    doc = html.fromstring(result)
    mo_elements = doc.xpath('//*[local-name()="mo"][@data-mjx-texclass="OP"]')
    assert mo_elements, "Expected at least one <mo data-mjx-texclass='OP'> element"
    for mo in mo_elements:
        assert mo.get("stretchy") == "false", (
            f"<mo data-mjx-texclass='OP'> must have stretchy='false', got {mo.get('stretchy')!r}"
        )
