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
| 1 | PDF version is 1.7; UA-2 requires PDF 2.0 | **Blocker** | Prince CSS / CLI flag |
| 2 | Missing `DisplayDocTitle` viewer preference | **Blocker** | pikepdf post-process |
| 3 | No PDF/UA identifier (`/Metadata` XMP with `pdfuaid:part=2`) | **Blocker** | pikepdf post-process |
| 4 | TOC `<div>` has no `role="navigation"` → untagged in PDF | **High** | `PrinceHtmlPreprocessor` ✓ |
| 5 | Chapter `<div>` elements lack `aria-label` → anonymous regions | **High** | `PrinceHtmlPreprocessor` ✓ |
| 6 | Math images have LaTeX in `alt` (not human-readable) | **High** | `HtmlProcessor` (spoken alt) ✓ |
| 7 | Math images should be replaced with `<math>` for Prince to tag as Formula | **High** | `HtmlProcessor` math conversion ✓ |
| 8 | `<html lang>` attribute absent (only `xml:lang`) → PDF language tag missing | **Medium** | `PrinceHtmlPreprocessor` ✓ |
| 9 | Decorative images already have `role="presentation"` | ✅ OK | — |
| 10 | Heading hierarchy (`h1` reused per chapter) may produce flat tag tree | **Medium** | Evaluate / Prince CSS |
| 11 | Tables may lack `<th>` scope attributes | **Medium** | Pressbooks / manual |
| 12 | Links missing explicit purpose if only icon | **Low** | Content review |

Items marked ✓ are already addressed by code in this repository.

---

## Detailed gap analysis

### Gap 1 — PDF version 1.7 vs. PDF 2.0 (Blocker)

**Standard requirement** (ISO 14289-2 §4): *A PDF/UA-2 file shall be a PDF 2.0 file.*

**Prince behaviour**: Prince defaults to PDF 1.7.  PDF 2.0 output can be
requested via the CSS property `@prince-pdf { prince-pdf-output-intent: sRGB; }` 
together with the CLI flag `--pdf-version=2` (Prince 15+).  Verify with:

```
prince input.html --pdf-version=2 -o output.pdf
```

If the installed Prince version does not support `--pdf-version=2`, a post-process
via pikepdf cannot upgrade the file — upgrading the Prince version is required.

### Gap 2 — `DisplayDocTitle` viewer preference (Blocker)

**Standard requirement** (ISO 14289-2 §7.1): The `ViewerPreferences` dictionary
must contain `DisplayDocTitle: true`.

**Current state**: The Prince-generated PDF likely omits or sets this to false.

**Fix via pikepdf**:

```python
import pikepdf
with pikepdf.Pdf.open("input.pdf", allow_overwriting_input=True) as pdf:
    vp = pdf.Root.get("/ViewerPreferences") or pikepdf.Dictionary()
    vp["/DisplayDocTitle"] = True
    pdf.Root["/ViewerPreferences"] = vp
    pdf.save("output.pdf")
```

Alternatively, Prince respects the CSS:
```css
@prince-pdf {
    prince-viewer-preferences: display-doc-title;
}
```

### Gap 3 — PDF/UA-2 XMP metadata identifier (Blocker)

**Standard requirement** (ISO 14289-2 §6.7.3): The file's XMP metadata stream
must declare `pdfuaid:part` = `2`.

**Fix**: Prince does not emit the `pdfuaid` namespace automatically for UA-2.
Post-process with pikepdf to extend the existing XMP packet, or inject it:

```python
xmp_template = b"""<?xpacket begin='\xef\xbb\xbf' id='W5M0MpCehiHzreSzNTczkc9d'?>
<x:xmpmeta xmlns:x='adobe:ns:meta/'>
  <rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>
    <rdf:Description rdf:about=''
        xmlns:pdfuaid='http://www.aiim.org/pdfua/ns/id/'>
      <pdfuaid:part>2</pdfuaid:part>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end='w'?>"""
```

### Gap 4 — TOC untagged as navigation (High) — already fixed

`PrinceHtmlPreprocessor` now adds `role="navigation"` and
`aria-label="Table of Contents"` to `<div id="toc">`, causing Prince to emit a
`Nav` (or `Part`) structure element for the TOC.

### Gap 5 — Anonymous chapter regions (High) — already fixed

Chapter, front-matter, and back-matter `<div>` elements now receive
`role="region"` and `aria-label` from their existing `title` attributes via
`PrinceHtmlPreprocessor`.

### Gap 6 — LaTeX alt text on math images (High) — already fixed

With `--spoken-alt-text`, `HtmlProcessor` instructs Speech Rule Engine to
produce plain-English descriptions which are then set as `aria-label` on the
generated `<math>` elements, giving assistive technology a human-readable
fallback alongside the full MathML tree.

### Gap 7 — Math images vs. MathML Formula tags (High) — already fixed

`HtmlProcessor` replaces `<img class="latex">` placeholders with `<math>`
elements.  Prince renders MathML natively and tags each `<math>` block as a
`Formula` structure element in the PDF tag tree.

### Gap 8 — Missing plain `lang` attribute (Medium) — already fixed

`PrinceHtmlPreprocessor._fix_html_lang` copies `xml:lang` to `lang` on the
root `<html>` element so that Prince propagates the document language
(`/Lang` entry) to the PDF catalogue.

### Gap 10 — Heading hierarchy (Medium)

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

### Gap 11 — Table header scope (Medium)

Data tables should have `<th scope="col">` or `<th scope="row">` attributes.
Pressbooks sometimes generates tables without explicit scopes.  A table scan
pass in `PrinceHtmlPreprocessor` could add `scope="col"` to `<th>` elements
that lack it (defaulting to column headers is usually correct for simple
tables).

### Gap 12 — Link purpose (Low)

PDF/UA-2 requires that links have a discernible purpose (ISO 14289-2 §7.18.5).
Icon-only links (e.g. social media icons) need `aria-label`.  This is a
content-authoring concern; a preprocessor could flag missing labels but cannot
reliably supply them.

---

## Recommended post-processing pipeline for PDF/UA-2

For a fully automated pipeline using the existing tooling:

```
Pressbooks HTML
  ↓  HtmlProcessor (--math-backend mathjax)
  ↓  PrinceHtmlPreprocessor (--prince-preprocess)
  ↓  [optionally: --spoken-alt-text]
  ↓  Prince XML (--pdf-version=2)
  ↓  pikepdf post-processor
        • Set DisplayDocTitle = true
        • Inject pdfuaid:part = 2 into XMP
  ↓  veraPDF validation (PDF/UA-2 profile)
```

The pikepdf post-processing steps are small and can be added as a
`converters/prince_pdf_postprocessor.py` module following the same pattern as
the existing `converters/pdf_mathml_postprocessor.py`.

---

## Open questions

1. **Prince version**: Does the installed Prince support `--pdf-version=2`?
   Prince 15 (released 2023) added PDF 2.0 output.  Older installs are stuck
   at PDF 1.7 and cannot produce PDF/UA-2 without an upgrade.

2. **MathML AF entries**: PDF/UA-2 recommends MathML as Associated Files on
   `Formula` structure elements (ISO 14289-2 Annex A).  Prince may embed
   MathML AF entries automatically when processing `<math>` elements in
   PDF 2.0 mode — this needs direct testing.  If not, the existing
   `pdf_mathml_postprocessor.py` approach (pikepdf injection) can be adapted.

3. **veraPDF profile**: The PDF/UA-2 veraPDF profile is available from
   `verapdf.org`.  Once a Prince 2.0 PDF is produced, running veraPDF with
   `--flavour ua2` will give a definitive list of remaining failures.
