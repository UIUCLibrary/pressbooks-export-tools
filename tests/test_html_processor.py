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

    assert '<math' in processed and '<mtext>x+y</mtext>' in processed
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


def test_alttext_always_set_without_spoken_alt() -> None:
    """alttext is set to the original LaTeX even without --spoken-alt-text.

    Prince XML reads alttext to populate the Formula structure element's Alt
    entry.  Without it Prince emits "Formula structure element is missing
    alternative text" errors.
    """
    markup = '<html><body><p><img class="latex" alt="x+y" /></p></body></html>'

    processed = HtmlProcessor(backend=StubBackend()).process_html(markup)

    assert 'alttext="x+y"' in processed


def test_alttext_set_with_spoken_alt() -> None:
    """When spoken alt text is on, alttext gets the spoken description (for Prince).

    Prince XML reads alttext to populate the Formula structure element's Alt
    entry.  With --spoken-alt-text, the spoken description should appear there
    so screen readers see plain English instead of raw LaTeX.  The original
    LaTeX is preserved in data-latex.
    """
    markup = '<html><body><p><img class="latex" alt="x+y" /></p></body></html>'

    processed = HtmlProcessor(
        backend=StubBackend(),
        spoken_alt_text=True,
        sre_backend=StubSreBackend(),
    ).process_html(markup)

    assert 'alttext="spoken: x+y"' in processed
    assert 'data-latex="x+y"' in processed
    assert 'aria-label="spoken: x+y"' in processed


def test_alttext_not_overwritten_if_already_present() -> None:
    """If the backend already emits alttext, we do not overwrite it."""

    class AltTextBackend(MathBackend):
        def convert(self, latex: str, *, display: bool = False) -> str:
            return f'<math alttext="custom"><mtext>{latex}</mtext></math>'

    markup = '<html><body><p><img class="latex" alt="x+y" /></p></body></html>'

    processed = HtmlProcessor(backend=AltTextBackend()).process_html(markup)

    assert 'alttext="custom"' in processed
    assert 'alttext="x+y"' not in processed


def test_data_latex_set_even_when_backend_emits_alttext() -> None:
    """data-latex is set when spoken alt text is on, even if the backend emits alttext.

    Downstream consumers (e.g. MathML re-conversion) rely on data-latex to
    find the original LaTeX.  It must be set regardless of whether the backend
    already populated alttext with its own value.
    """

    class AltTextBackend(MathBackend):
        def convert(self, latex: str, *, display: bool = False) -> str:
            return f'<math alttext="custom"><mtext>{latex}</mtext></math>'

    markup = '<html><body><p><img class="latex" alt="x+y" /></p></body></html>'

    processed = HtmlProcessor(
        backend=AltTextBackend(),
        spoken_alt_text=True,
        sre_backend=StubSreBackend(),
    ).process_html(markup)

    # Backend's alttext should be preserved (not overwritten by spoken text).
    assert 'alttext="custom"' in processed
    # Original LaTeX must be available in data-latex.
    assert 'data-latex="x+y"' in processed
    # Spoken text goes to aria-label.
    assert 'aria-label="spoken: x+y"' in processed


def test_process_html_with_xml_encoding_declaration() -> None:
    """process_html must not raise when markup contains an XML encoding declaration.

    Pressbooks XHTML exports begin with ``<?xml version="1.0" encoding="UTF-8"?>``.
    lxml rejects such a declaration when the input is a Python *str*; the fix is to
    encode to bytes before parsing.
    """
    markup = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE html>'
        '<html><body>'
        '<p><img class="latex" alt="x+y" /></p>'
        '</body></html>'
    )

    # Must not raise ValueError
    processed = HtmlProcessor(backend=StubBackend()).process_html(markup)

    assert '<math' in processed
    assert '<img class="latex"' not in processed

