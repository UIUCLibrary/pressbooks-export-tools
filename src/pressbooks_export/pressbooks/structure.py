from __future__ import annotations

from lxml import html


def extract_title(document: html.HtmlElement) -> str | None:
    for expression in ['//meta[@property="og:title"]/@content', '//title/text()', '//h1[1]/text()']:
        values = [value.strip() for value in document.xpath(expression) if value and value.strip()]
        if values:
            return values[0]
    return None
