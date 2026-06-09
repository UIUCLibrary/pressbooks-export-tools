# pressbooks-export-tools

`pressbooks-export-tools` is a scaffold for a Python-first export pipeline that turns Pressbooks HTML exports into accessible PDF and ODT outputs.

## Project goal

Pressbooks webbooks render equations with MathJax in the browser, but Pressbooks HTML exports typically downgrade those equations to image tags with the original LaTeX preserved in the `alt` attribute. This project restores that math to MathML so downstream PDF and ODT exports can aim for parity with the webbook experience.

## Planned pipeline

1. Parse Pressbooks HTML exports.
2. Detect math images such as `<img class="latex" alt="...">`.
3. Convert the LaTeX in `alt` text to MathML with MathJax for Node.js (primary) or `latex2mathml` (fallback).
4. Replace math images with `<math>` elements.
5. Send processed HTML to:
   - Pandoc for ODT output
   - WeasyPrint for PDF output

## Repository scaffold

- `src/pressbooks_export/`: Python package and CLI scaffold.
- `spike/`: proof-of-concept assets for validating MathML-in-PDF output with stakeholders and accessibility experts.
- `tests/`: focused scaffold tests.
- `docs/`: architecture and math-handling notes.
- `.github/workflows/ci.yml`: starter CI workflow.

## Phase 0 spike

Before production implementation, the repository includes a spike that exercises a representative equation set through the proposed MathJax → HTML → WeasyPrint → veraPDF pipeline.

Validation targets:

- visual review of representative equations
- accessibility review with assistive technology
- PDF/UA validation with veraPDF

See `/home/runner/work/pressbooks-export-tools/pressbooks-export-tools/UIUCLibrary/pressbooks-export-tools/spike/README.md` for the spike checklist and usage notes.

## Quick start

```bash
python -m pip install -e ".[test]"
pytest
pb-export --help
```

Optional extras:

- `.[math]` for the Python LaTeX fallback backend
- `.[pdf]` for WeasyPrint support
- `.[odt]` for Pandoc wrapper support
- `.[all]` for the full Python dependency set
