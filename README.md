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

See `spike/README.md` for the spike checklist and usage notes.

## Installation

### Development (editable) install

Create a virtual environment and install the package in editable mode:

```bash
python3 -m venv /path/to/venv
/path/to/venv/bin/pip install -e ".[test]"
```

Replace `/path/to/venv` with a directory you have write access to (e.g. `~/.venv/pb-tools` or `/opt/pb-venv`).

> **Note:** If you previously ran the install as a different user (e.g. with `sudo`), you may see a
> `Cannot update time stamp of directory 'src/pressbooks_export_tools.egg-info'` error.
> Delete that directory and retry:
> ```bash
> sudo rm -rf src/pressbooks_export_tools.egg-info
> /path/to/venv/bin/pip install -e ".[test]"
> ```

### Install from GitHub

```bash
/path/to/venv/bin/pip install "git+https://github.com/UIUCLibrary/pressbooks-export-tools.git"
```

### Quick start

```bash
pytest
pb-export --help
```

### Optional extras

- `.[math]` for the Python LaTeX fallback backend
- `.[pdf]` for WeasyPrint support
- `.[odt]` for Pandoc wrapper support
- `.[all]` for the full Python dependency set
