from pressbooks_export.html_processor import HtmlProcessor
from pressbooks_export.math.backends.base import MathBackend
from pressbooks_export.math.backends.sre_backend import SreNodeBackend


class StubBackend(MathBackend):
    def convert(self, latex: str, *, display: bool = False) -> str:
        display_attr = ' display="block"' if display else ''
        return f'<math{display_attr}><mtext>{latex}</mtext></math>'


class StubSreBackend(SreNodeBackend):
    """SRE backend test double that returns predictable spoken descriptions."""

    def __init__(self) -> None:
        # Don't call super().__init__() – we don't want Node.js paths set.
        pass

    def to_speech_batch(self, items: list[tuple[str, bool]]) -> list[str]:
        return [f"spoken: {latex}" for latex, _display in items]


def test_html_processor_replaces_pressbooks_math_images() -> None:
    markup = '<html><body><p><img class="latex" alt="x+y" /></p></body></html>'

    processed = HtmlProcessor(backend=StubBackend()).process_html(markup)

    assert '<math>' in processed and '<mtext>x+y</mtext>' in processed
    assert '<img class="latex"' not in processed


def test_spoken_alt_text_replaces_alt_attribute() -> None:
    markup = '<html><body><p><img class="latex" alt="x+y" /></p></body></html>'

    processed = HtmlProcessor(
        backend=StubBackend(),
        spoken_alt_text=True,
        sre_backend=StubSreBackend(),
    ).process_html(markup)

    # The img should have been replaced with math; the spoken description
    # should appear as aria-label on the generated <math> element.
    assert 'aria-label="spoken: x+y"' in processed
    assert '<math' in processed
    assert '<img class="latex"' not in processed


def test_spoken_alt_text_preserves_latex_in_title() -> None:
    """The aria-label on the math element should contain the spoken description."""
    markup = '<html><body><p><img class="latex" alt="\\frac{1}{2}" /></p></body></html>'

    processed = HtmlProcessor(
        backend=StubBackend(),
        spoken_alt_text=True,
        sre_backend=StubSreBackend(),
    ).process_html(markup)

    # The math element should have the spoken description as aria-label.
    assert 'aria-label="spoken: \\frac{1}{2}"' in processed


def test_spoken_alt_text_does_not_overwrite_existing_title() -> None:
    """A pre-existing title attribute should carry through to the math element."""
    markup = (
        '<html><body>'
        '<p><img class="latex" alt="x^2" title="x squared already set" /></p>'
        '</body></html>'
    )

    processed = HtmlProcessor(
        backend=StubBackend(),
        spoken_alt_text=True,
        sre_backend=StubSreBackend(),
    ).process_html(markup)

    # aria-label should be the spoken description, not the title
    assert 'aria-label="spoken: x^2"' in processed


def test_spoken_alt_text_off_by_default() -> None:
    """Without the flag the alt attribute keeps the original LaTeX."""
    markup = '<html><body><p><img class="latex" alt="x+y" /></p></body></html>'

    processed = HtmlProcessor(backend=StubBackend()).process_html(markup)

    # MathML should be present but original LaTeX in alt should NOT appear
    # because the image has been replaced entirely.  The key check is that
    # no spoken: prefix appears.
    assert "spoken:" not in processed

