from lxml import html

from pressbooks_export.pressbooks.structure import extract_title


def test_extract_title_prefers_metadata() -> None:
    document = html.fromstring(
        '<html><head><meta property="og:title" content="Exported Book" /><title>Ignored</title></head><body><h1>Ignored</h1></body></html>'
    )

    assert extract_title(document) == "Exported Book"
