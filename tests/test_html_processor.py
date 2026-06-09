from pressbooks_export.html_processor import HtmlProcessor
from pressbooks_export.math.backends.base import MathBackend


class StubBackend(MathBackend):
    def convert(self, latex: str, *, display: bool = False) -> str:
        display_attr = ' display="block"' if display else ''
        return f'<math{display_attr}><mtext>{latex}</mtext></math>'


def test_html_processor_replaces_pressbooks_math_images() -> None:
    markup = '<html><body><p><img class="latex" alt="x+y" /></p></body></html>'

    processed = HtmlProcessor(backend=StubBackend()).process_html(markup)

    assert '<math><mtext>x+y</mtext></math>' in processed
    assert '<img class="latex"' not in processed
