from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from lxml import html

REPO_ROOT = Path(__file__).resolve().parent.parent
SPIKE_ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Pressbooks MathML accessibility spike")
    parser.add_argument("--input", default=SPIKE_ROOT / "test_equations.html", type=Path)
    parser.add_argument("--output-dir", default=SPIKE_ROOT / "output", type=Path)
    parser.add_argument("--skip-pdf", action="store_true")
    parser.add_argument("--verapdf", type=Path, default=None)
    return parser.parse_args()


def convert_with_mathjax(latex: str, display: bool) -> str:
    payload = json.dumps({"latex": latex, "display": display})
    completed = subprocess.run(
        ["node", str(SPIKE_ROOT / "mathjax_convert.mjs")],
        check=True,
        input=payload,
        text=True,
        capture_output=True,
    )
    data = json.loads(completed.stdout)
    return data["mathml"]


def process_html(input_path: Path, output_path: Path) -> None:
    document = html.fromstring(input_path.read_text(encoding="utf-8"))
    for element in document.xpath('//img[contains(concat(" ", normalize-space(@class), " "), " latex ")]'):
        latex = (element.get("alt") or "").strip()
        if not latex:
            continue
        replacement = html.fragment_fromstring(
            convert_with_mathjax(latex, element.get("data-display") == "block"),
            create_parent=False,
        )
        parent = element.getparent()
        if parent is None:
            continue
        parent.replace(element, replacement)
    output_path.write_text(html.tostring(document, encoding="unicode", pretty_print=True), encoding="utf-8")


def generate_pdf(input_path: Path, output_path: Path) -> None:
    from weasyprint import HTML

    HTML(filename=str(input_path), base_url=str(input_path.parent)).write_pdf(str(output_path))


def run_verapdf(pdf_path: Path, output_dir: Path, requested_binary: Path | None) -> Path | None:
    binary = str(requested_binary) if requested_binary else shutil.which("verapdf")
    if not binary:
        return None
    report_path = output_dir / "verapdf-report.xml"
    with report_path.open("w", encoding="utf-8") as handle:
        subprocess.run([binary, str(pdf_path)], check=False, stdout=handle, stderr=subprocess.STDOUT, text=True)
    return report_path


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    processed_html = args.output_dir / "processed-equations.html"
    process_html(args.input, processed_html)
    print(f"Processed HTML written to {processed_html}")

    if args.skip_pdf:
        return

    pdf_path = args.output_dir / "pressbooks-math-spike.pdf"
    generate_pdf(processed_html, pdf_path)
    print(f"PDF written to {pdf_path}")

    report_path = run_verapdf(pdf_path, args.output_dir, args.verapdf)
    if report_path:
        print(f"veraPDF report written to {report_path}")
    else:
        print("veraPDF not found on PATH; skipping PDF/UA validation")


if __name__ == "__main__":
    main()
