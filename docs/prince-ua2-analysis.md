# Prince XML → PDF/UA-2 Gap Analysis

## Context

The example document `example_documents/Introduction-to-Basic-Probability-1782243240-2.pdf`
was produced by Prince XML from the companion HTML file using Pressbooks' native
export settings.  This document analyses what would be required to turn that
Prince output (a PDF 1.7 file) into a fully PDF/UA-2 compliant document.

PDF/UA-2 is defined in ISO 14289-2:2024.  It is built on PDF 2.0 (ISO 32000-2)
rather than PDF 1.7.  Every PDF/UA-2 file must therefore be a PDF 2.0 file.

---

## Summary of gaps

| # | Gap | Severity | Fix location |
|---|-----|----------|--------------|
| 1 | PDF version is 1.7; UA-2 requires PDF 2.0 | **Blocker** | Prince upgrade (unconfirmed) / post-process |
| 2 | Missing `DisplayDocTitle` viewer preference | **Blocker** | `converters/prince_pdf_postprocessor.py` ✓ |
| 3 | No PDF/UA identifier (`/Metadata` XMP with `pdfuaid:part=2`) | **Blocker** | `converters/prince_pdf_postprocessor.py` ✓ |
| 4 | Math images missing `role="math"` → not tagged as Formula in PDF | **Blocker** | `PrinceHtmlPreprocessor` ✓ |
| 5 | Math images have LaTeX in `alt` (not human-readable) | **High** | `PrinceHtmlPreprocessor` (spoken alt) ✓ |
| 6 | TOC `<div>` has no `role="navigation"` → untagged in PDF | **High** | Deferred — see GitHub issue |
| 7 | Chapter `<div>` elements lack `aria-label` → anonymous regions | **High** | Deferred — see GitHub issue |
| 8 | Math images should be replaced with `<math>` for Prince to tag as Formula | **High** | `HtmlProcessor` math conversion ✓ |
| 9 | `<html lang>` attribute absent (only `xml:lang`) → PDF language tag missing | **Medium** | `PrinceHtmlPreprocessor` ✓ |
| 10 | Decorative images already have `role="presentation"` | ✅ OK | — |
| 11 | Heading hierarchy (`h1` reused per chapter) may produce flat tag tree | **Medium** | Evaluate / Prince CSS |
| 12 | Tables may lack `<th>` scope attributes | **Medium** | Pressbooks / manual |
| 13 | Links missing explicit purpose if only icon | **Low** | Content review |

Items marked ✓ are already addressed by code in this repository.

---

## Detailed gap analysis

### Gap 1 — PDF version 1.7 vs. PDF 2.0 (Blocker)

**Standard requirement** (ISO 14289-2 §4): *A PDF/UA-2 file shall be a PDF 2.0 file.*

**Prince behaviour**: Prince defaults to PDF 1.7.  The documentation for Prince 15
(`https://www.princexml.com/doc/15/prince-output/`) should be consulted to confirm
whether `--pdf-version=2` is supported in that release.  Based on current information
this support has **not been confirmed** — upgrading to the latest Prince release is
recommended and should be tested directly.

If the installed Prince version does not support `--pdf-version=2`, a post-process
via pikepdf **cannot meaningfully upgrade the file** — upgrading the Prince version
is required for a proper PDF 2.0 structure.

As a stopgap, `converters/prince_pdf_postprocessor.py` addresses the two other
PDF/UA-2 blockers (Gaps 2 and 3) regardless of PDF version, so that the document
is as close to compliant as possible given the available tooling.

### Gap 2 — `DisplayDocTitle` viewer preference (Blocker) — fixed

**Standard requirement** (ISO 14289-2 §7.1): The `ViewerPreferences` dictionary
must contain `DisplayDocTitle: true`.

**Fix**: `converters/prince_pdf_postprocessor.postprocess_for_pdfua2()` sets this
via pikepdf after Prince generates the PDF:

```python
from pressbooks_export.converters.prince_pdf_postprocessor import postprocess_for_pdfua2
postprocess_for_pdfua2(Path("output.pdf"))
```

Alternatively, Prince respects the CSS:
```css
@prince-pdf {
    prince-viewer-preferences: display-doc-title;
}
```

### Gap 3 — PDF/UA-2 XMP metadata identifier (Blocker) — fixed

**Standard requirement** (ISO 14289-2 §6.7.3): The file's XMP metadata stream
must declare `pdfuaid:part` = `2`.

**Fix**: `converters/prince_pdf_postprocessor.postprocess_for_pdfua2()` injects
or merges this declaration into the PDF's XMP metadata stream via pikepdf.  If an
existing `/Metadata` stream is present, the `pdfuaid` block is merged into it;
otherwise a complete minimal XMP packet is written.

### Gap 4 — Math images missing `role="math"` (Blocker) — fixed

`PrinceHtmlPreprocessor._add_math_roles` adds `role="math"` to:

* `<img class="latex">` placeholders (when the preprocessor runs before math
  conversion).
* `<math>` elements (when the preprocessor runs after `HtmlProcessor`).

Prince uses `role="math"` to tag these elements as `Formula` structure elements
in the PDF tag tree, which is required for PDF/UA-2 math accessibility.

### Gap 5 — LaTeX alt text on math images (High) — fixed

With `--prince-preprocess --spoken-alt-text`, `PrinceHtmlPreprocessor` instructs
Speech Rule Engine to produce plain-English spoken descriptions for each
`<img class="latex">` element.  The spoken text replaces the LaTeX in `alt`;
the original LaTeX is preserved in a `data-latex` attribute so that downstream
MathML conversion (`HtmlProcessor`) can still locate the source expression.

`HtmlProcessor` also sets `aria-label` on generated `<math>` elements when
`--spoken-alt-text` is active, giving assistive technology a human-readable
fallback alongside the full MathML tree.

### Gap 6 — TOC untagged as navigation (High) — deferred

Adding `role="navigation"` and `aria-label="Table of Contents"` to
`<div id="toc">` was prototyped but deferred for evaluation.  See the open
GitHub issue for scope, open questions, and evaluation criteria.

### Gap 7 — Anonymous chapter regions (High) — deferred

Chapter, front-matter, and back-matter `<div>` elements gaining `role="region"`
and `aria-label` was prototyped but deferred for evaluation.  See the open
GitHub issue.

### Gap 8 — Math images vs. MathML Formula tags (High) — already fixed

`HtmlProcessor` replaces `<img class="latex">` placeholders with `<math>`
elements.  Prince renders MathML natively and tags each `<math>` block as a
`Formula` structure element in the PDF tag tree.

### Gap 9 — Missing plain `lang` attribute (Medium) — already fixed

`PrinceHtmlPreprocessor._fix_html_lang` copies `xml:lang` to `lang` on the
root `<html>` element so that Prince propagates the document language
(`/Lang` entry) to the PDF catalogue.

### Gap 11 — Heading hierarchy (Medium)

Each Pressbooks chapter restarts `<h1>` for the chapter title.  In a
single-page export this produces a flat `H1 → H2 → H3 …` structure repeated
across chapters without a wrapping `<section>` or `<article>` element to
separate them.  Prince will produce a valid tag tree (all headings appear at
the level the HTML declares), but PDF/UA-2 validators may flag heading levels
that do not reflect the actual document hierarchy.

**Options**:
- Add `role="heading" aria-level="N"` attributes to adjust perceived heading
  levels without changing the visible style (preprocessor approach).
- Request Pressbooks to use `<section>` wrappers so that `<h1>` inside each
  section is correctly treated as a nested heading.
- Adjust CSS `prince-pdf-tag-type` to remap `H1` within chapter wrappers to
  the correct heading level.

This is a medium-priority issue; most screen readers handle repeated `H1` in
sectioned content gracefully, and validators typically issue warnings rather
than errors for this pattern.

### Gap 12 — Table header scope (Medium)

Data tables should have `<th scope="col">` or `<th scope="row">` attributes.
Pressbooks sometimes generates tables without explicit scopes.  A table scan
pass in `PrinceHtmlPreprocessor` could add `scope="col"` to `<th>` elements
that lack it (defaulting to column headers is usually correct for simple
tables).

### Gap 13 — Link purpose (Low)

PDF/UA-2 requires that links have a discernible purpose (ISO 14289-2 §7.18.5).
Icon-only links (e.g. social media icons) need `aria-label`.  This is a
content-authoring concern; a preprocessor could flag missing labels but cannot
reliably supply them.

---

## Recommended post-processing pipeline for PDF/UA-2

For a fully automated pipeline using the existing tooling:

```
Pressbooks HTML
  ↓  HtmlProcessor (--math-backend mathjax [--spoken-alt-text])
  ↓  PrinceHtmlPreprocessor (--prince-preprocess [--spoken-alt-text])
        • Adds role="math" to <img class="latex"> and <math> elements
        • Optionally replaces LaTeX alt with spoken text (data-latex preserved)
        • Copies xml:lang → lang
  ↓  Prince XML (--pdf-version=2 if supported)
  ↓  prince_pdf_postprocessor.postprocess_for_pdfua2()
        • Set DisplayDocTitle = true
        • Inject pdfuaid:part = 2 into XMP
  ↓  veraPDF validation (PDF/UA-2 profile)
```

The pikepdf post-processing steps are small and can be added as a
`converters/prince_pdf_postprocessor.py` module following the same pattern as
the existing `converters/pdf_mathml_postprocessor.py`.

---

## Open questions

1. **Prince version and PDF 2.0**: Does the currently installed Prince support
   `--pdf-version=2`?  Prince 15's support for this flag has not been confirmed.
   Check the Prince 15 release notes at `https://www.princexml.com/doc/15/prince-output/`
   and test directly.  If Prince 15 does not produce PDF 2.0, a later release or a
   different tool (PDFreactor, Antenna House) may be required for Gap 1.

2. **MathML AF entries**: PDF/UA-2 recommends MathML as Associated Files on
   `Formula` structure elements (ISO 14289-2 Annex A).  Prince may embed
   MathML AF entries automatically when processing `<math>` elements in
   PDF 2.0 mode — this needs direct testing.  If not, the existing
   `pdf_mathml_postprocessor.py` approach (pikepdf injection) can be adapted.

3. **veraPDF profile**: The PDF/UA-2 veraPDF profile is available from
   `verapdf.org`.  Once a Prince PDF 2.0 output is produced, running veraPDF with
   `--flavour ua2` will give a definitive list of remaining failures.

4. **Deferred landmark roles**: TOC navigation, chapter regions, copyright
   contentinfo — see the open GitHub issue for evaluation criteria and open
   questions about Prince tag-type behaviour.
