from pathlib import Path

from lxml import html

from pressbooks_export.math.detector import find_latex_images


FIXTURE = Path(__file__).parent / "fixtures" / "sample_pressbooks_export.html"


def test_find_latex_images_ignores_images_without_alt_text() -> None:
    document = html.fromstring(FIXTURE.read_text(encoding="utf-8"))

    matches = find_latex_images(document)

    assert [match.latex for match in matches] == ["x^2 + y^2 = z^2", "\\frac{1}{2}"]
    assert [match.display for match in matches] == [False, True]


def test_find_latex_images_prefers_data_latex_over_alt() -> None:
    """data-latex (set by PrinceHtmlPreprocessor) takes priority over alt."""
    markup = (
        '<html><body>'
        '<p><img class="latex" alt="x squared" data-latex="x^2" /></p>'
        '</body></html>'
    )
    document = html.fromstring(markup)
    matches = find_latex_images(document)
    assert len(matches) == 1
    assert matches[0].latex == "x^2"


def test_find_latex_images_falls_back_to_alt_without_data_latex() -> None:
    markup = (
        '<html><body>'
        '<p><img class="latex" alt="x^2" /></p>'
        '</body></html>'
    )
    document = html.fromstring(markup)
    matches = find_latex_images(document)
    assert len(matches) == 1
    assert matches[0].latex == "x^2"

