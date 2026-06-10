from __future__ import annotations

from pathlib import Path

import click

from .converters.odt import PandocOdtConverter
from .converters.pdf import PandocLuaLatexPdfConverter
from .html_processor import HtmlProcessor
from .math.backends.latex2mathml_backend import Latex2MathMLBackend
from .math.backends.mathjax_backend import MathJaxNodeBackend


@click.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option("--format", "output_format", type=click.Choice(["html", "pdf", "odt"]), default="html", show_default=True)
@click.option("--output", "output_path", type=click.Path(path_type=Path), required=True)
@click.option(
    "--math-backend",
    type=click.Choice(["mathjax", "latex2mathml"]),
    default="mathjax",
    show_default=True,
)
def main(input_path: Path, output_format: str, output_path: Path, math_backend: str) -> None:
    """Process a Pressbooks HTML export into HTML, PDF, or ODT."""
    processor = HtmlProcessor(
        backend=MathJaxNodeBackend() if math_backend == "mathjax" else Latex2MathMLBackend()
    )
    processed_html = processor.process_file(input_path)

    if output_format == "html":
        output_path.write_text(processed_html, encoding="utf-8")
        click.echo(f"Wrote processed HTML to {output_path}")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_html = output_path.with_suffix(".processed.html")
    temp_html.write_text(processed_html, encoding="utf-8")

    if output_format == "pdf":
        PandocLuaLatexPdfConverter().convert_html(temp_html, output_path)
    else:
        PandocOdtConverter().convert_html(temp_html, output_path)

    click.echo(f"Wrote {output_format.upper()} output to {output_path}")
