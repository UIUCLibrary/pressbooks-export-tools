from pathlib import Path

from lxml import html

from pressbooks_export.math.detector import find_latex_images


FIXTURE = Path(__file__).parent / "fixtures" / "sample_pressbooks_export.html"


def test_find_latex_images_ignores_images_without_alt_text() -> None:
    document = html.fromstring(FIXTURE.read_text(encoding="utf-8"))

    matches = find_latex_images(document)

    assert [match.latex for match in matches] == ["x^2 + y^2 = z^2", "\\frac{1}{2}"]
    assert [match.display for match in matches] == [False, True]
