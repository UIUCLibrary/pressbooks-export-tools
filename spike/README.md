# MathML accessibility spike

This spike is the first milestone for the repository. Its purpose is to validate, with stakeholders and accessibility reviewers, that the planned MathJax-to-PDF pipeline is good enough before production implementation proceeds.

## Pipeline overview

```
Pressbooks HTML (with LaTeX in img alt)
    ↓
[MathJax Node.js] Convert LaTeX → MathML
    ↓
Processed HTML (with inline MathML)
    ↓
[Pandoc] Convert HTML → LaTeX (MathML → LaTeX math)
    ↓
[LuaLaTeX] Compile to PDF
    ↓
PDF with rendered math equations
```

## Representative equation set

1. simple inline equation
2. quadratic formula
3. summation
4. integral with bounds
5. Greek letters and bold symbols
6. matrix multiplication
7. aligned multi-line equation
8. nested inequality with stretchy delimiters

## Validation checklist

- [x] Produce processed HTML with `<math>` elements from exported Pressbooks-style math images.
- [x] Generate a PDF from the processed HTML using Pandoc + LuaLaTeX.
- [ ] Run veraPDF and capture a report for accessibility review.
- [ ] Share the PDF with stakeholders for visual validation.
- [ ] Share the PDF with accessibility reviewers for assistive-technology validation.

## Usage

```bash
# Install dependencies
pip install -r spike/requirements.txt
npm install --prefix spike

# Run the spike (generates HTML and PDF)
python spike/run_spike.py --output-dir spike/output

# Keep intermediate files for debugging
python spike/run_spike.py --output-dir spike/output --keep-intermediates

# Skip PDF generation (HTML only)
python spike/run_spike.py --output-dir spike/output --skip-pdf
```

If `verapdf` is on your `PATH`, the spike runner will call it automatically after PDF generation.

## Output files

With `--keep-intermediates`, the spike generates:

| File | Description |
|------|-------------|
| `processed-equations.html` | HTML with MathML (validates browser rendering) |
| `pressbooks-math-spike.tex` | Intermediate LaTeX source (validates Pandoc conversion) |
| `pressbooks-math-spike.pdf` | Final PDF output |

## Reference examples

The `reference/` directory contains hand-crafted LaTeX documents with the same equations, serving as the "gold standard" for PDF output quality.

### External reference PDFs (PDF/UA-2 with MathML)

The LaTeX3 tagging-project provides validated PDF/UA-2 examples:

- **PDF/UA-2 Examples**: https://github.com/latex3/tagging-project/discussions/72
- **MathML Associated Files**: https://github.com/latex3/tagging-project/discussions/56
- **PDF/UA-1 Examples (PDF 1.7)**: https://github.com/latex3/tagging-project/discussions/82
- **Google Drive (downloadable PDFs)**: https://drive.google.com/drive/folders/17iGeBcboFMx410H1Rozhb-Io-cp0f3TB

### Best practices documentation

- **PDF Association Best Practice Guide: Math in PDF**: https://pdfa.org/resource/best-practice-guide-math-in-pdf/
- **TAMU PDF/UA-2 Guide**: https://esail.tamu.edu/faculty-tutorials/accessible-latex-pdf-ua-2-overleaf-2025/

## Current limitations

1. **WeasyPrint removed**: WeasyPrint does not support MathML. We now use Pandoc + LuaLaTeX.

2. **PDF/UA-2 tagging enabled**: The pipeline uses a custom Pandoc template (`ua2-template.latex`) that emits `\DocumentMetadata{tagging=on, pdfstandard=ua-2}` before `\documentclass`. The converter prefers `lualatex-dev` (TeX Live 2025+) for full tagging support, falling back to `lualatex` when it is not available.

3. **MathML Associated Files not yet implemented**: Full PDF/UA-2 compliance with MathML associated files on Formula structure elements requires additional work (Pandoc Lua filter to retain MathML through the conversion).

3. **Screen reader support varies**:
   - Windows: NVDA + MathCAT works with MathML in PDFs
   - macOS: VoiceOver does not yet support MathML in PDFs
   - Firefox will soon support MathML in PDFs

## Future work

To achieve full PDF/UA-2 compliance, see the [math-handling documentation](../docs/math-handling.md).
