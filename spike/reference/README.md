# Reference PDF Examples

This directory contains reference LaTeX documents that demonstrate proper math rendering in PDFs.

## Files

### `reference_simple.tex` / `reference_simple.pdf`
A simple LaTeX document with the same equations as `test_equations.html`, compiled with LuaLaTeX. This serves as the "gold standard" for what the PDF output should look like.

### `reference_equations.tex` / `reference_equations.pdf`
Same content but with experimental PDF 2.0 tagging via the `tagpdf` package. This demonstrates the direction for future PDF/UA-2 compliance.

## How to regenerate

```bash
cd spike/reference
lualatex reference_simple.tex
lualatex reference_equations.tex
```

## External reference examples

The LaTeX3 tagging-project provides validated PDF/UA-2 examples with MathML associated files:

- **PDF/UA-2 Examples collection**: https://github.com/latex3/tagging-project/discussions/72
- **MathML Associated Files discussion**: https://github.com/latex3/tagging-project/discussions/56
- **Google Drive with downloadable PDFs**: https://drive.google.com/drive/folders/17iGeBcboFMx410H1Rozhb-Io-cp0f3TB

These examples demonstrate:
- Each formula tagged with LaTeX source + MathML associated files
- PDF/UA-2, PDF/A-4F, WTPDF/Accessibility compliance
- Screen reader compatibility (tested with NVDA + MathCAT)

## Future work

To achieve full PDF/UA-2 compliance with MathML associated files, we would need to:

1. Use `lualatex-dev` from TeX Live 2025+
2. Add `\DocumentMetadata{}` to enable tagging infrastructure
3. Generate MathML files for each equation (we already have this via MathJax)
4. Associate the MathML files with Formula structure elements in the PDF

This is an active area of development in the LaTeX community.
