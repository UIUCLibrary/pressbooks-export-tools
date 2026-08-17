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
/path/to/venv/bin/pb-export --help
/path/to/venv/bin/pb-postprocess-pdf --help
```

> **Important:** The CLI scripts (`pb-export`, `pb-postprocess-pdf`,
> `pb-extract-latex`) are installed into the virtual environment's `bin/`
> directory.  They are **not** on your system `PATH` unless you activate the
> venv first (`source /path/to/venv/bin/activate`) or invoke them with their
> full path.  Running `pb-postprocess-pdf` without activating the venv or
> using the full path will produce a `command not found` error.

### Optional extras

- `.[math]` for the Python LaTeX fallback backend
- `.[pdf]` for `pb-postprocess-pdf` PDF/UA-2 post-processing support (pikepdf)
- `.[odt]` for Pandoc wrapper support
- `.[all]` for the full Python dependency set

## CLI reference

### `pb-export`

Converts a Pressbooks HTML export to HTML, PDF, or ODT.

```bash
/path/to/venv/bin/pb-export INPUT_PATH --format html --output output.html
/path/to/venv/bin/pb-export INPUT_PATH --format html --output output.html --prince-preprocess
```

### `pb-postprocess-pdf`

Applies PDF/UA-2 post-processing fixes to a Prince-generated PDF.  Requires
the `[pdf]` extra (`pip install '.[pdf]'` or `pip install '.[all]'`).

```bash
# Patch metadata in-place (DisplayDocTitle + pdfuaid:part=2 XMP):
/path/to/venv/bin/pb-postprocess-pdf /path/to/output.pdf

# Also attach MathML Associated Files from the processed HTML:
/path/to/venv/bin/pb-postprocess-pdf /path/to/output.pdf --html /path/to/clean.html

# Write to a new file instead of modifying the original:
/path/to/venv/bin/pb-postprocess-pdf /path/to/output.pdf \
    --html /path/to/clean.html \
    --output /path/to/patched.pdf
```

The `--html` option points at the **processed** HTML file that was fed to
Prince (the `clean.html` produced by `pb-export`), not the original dirty
export.  `pb-postprocess-pdf` reads the `<math>` elements from that file and
attaches them as Associated Files on the corresponding Formula structure
elements inside the PDF, satisfying the PDF/UA-2 accessibility requirement for
embedded MathML.

If you activated the virtual environment (`source /path/to/venv/bin/activate`)
you can omit the full path prefix:

```bash
pb-postprocess-pdf /path/to/output.pdf --html /path/to/clean.html
```

## Local debugging

`scripts/debug_local.sh` reproduces the exact command the WordPress plugin runs
(Step 2: `pb-export --format html --prince-preprocess`) so you can catch and fix
Python errors locally before deploying.

**Step 1 — get a real export HTML from the server:**

```bash
scp user@server:/var/www/html/wp-content/pb-export-debug/dirty.html \
    example_documents/dirty.html
```

(`dirty.html` is gitignored so large real exports are not committed accidentally.)

**Step 2 — run the debug script:**

```bash
./scripts/debug_local.sh
# or point at a specific file:
./scripts/debug_local.sh /path/to/dirty.html /tmp/clean.html
```

The script prints the full Python traceback on failure (no truncation), so errors
can be reproduced and fixed without needing access to the server.  Commit the fix,
`git pull` on the server, and repeat until the script exits 0.
