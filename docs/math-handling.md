# Math handling notes

## Terminology

- **Webbook**: the live Pressbooks browser experience where MathJax renders equations as MathML.
- **HTML export**: the static export where equations are often represented as images with LaTeX stored in `alt` text.
- **PDF/UA-2**: ISO 14289-2, the accessibility standard for PDF documents (released March 2024).
- **WTPDF**: "Well Tagged PDF" - PDF Association's framework for accessible and reusable PDF.
- **Associated Files**: PDF 2.0 feature allowing auxiliary files (like MathML) to be embedded and linked to structure elements.

## LaTeX-to-MathML conversion

### Backend priority

1. **MathJax for Node.js**: primary backend because it matches the webbook rendering engine.
2. **latex2mathml**: pure-Python fallback for constrained environments.

## PDF generation with accessible math

### The problem with WeasyPrint

WeasyPrint does not have native MathML support. It renders MathML as unstyled text or ignores it entirely, making it unsuitable for math-heavy documents.

### Recommended approach: LuaLaTeX with tagging

Based on the [LaTeX3 tagging-project](https://github.com/latex3/tagging-project/discussions/72), the correct approach for accessible math in PDFs is:

1. **Use Pandoc + LuaLaTeX**: Pandoc converts HTML with MathML to LaTeX, preserving math expressions. LuaLaTeX then renders the math properly.

2. **For PDF/UA-2 compliance** (future enhancement):
   - Use `lualatex-dev` from TeX Live 2025+
   - Enable tagging with `\DocumentMetadata{}`
   - Each formula can have two associated files:
     - LaTeX source fragment (for editability)
     - MathML document (for accessibility/screen readers)

### Current implementation

The spike uses a simpler pipeline that produces visually correct math:

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

### Intermediate files for debugging

The spike can generate intermediate files with `--keep-intermediates`:
- `processed-equations.html`: HTML with MathML (validates browser rendering)
- `pressbooks-math-spike.tex`: LaTeX source (validates Pandoc conversion)
- `pressbooks-math-spike.pdf`: Final PDF output

### Reference examples

The LaTeX3 project provides validated PDF/UA-2 examples with MathML:
- [PDF/UA-2 Examples](https://github.com/latex3/tagging-project/discussions/72)
- [MathML Associated Files discussion](https://github.com/latex3/tagging-project/discussions/56)

These examples demonstrate the target quality for accessible math in PDFs and can be used as reference when evaluating output.

## Accessibility spike focus

The spike validates:
1. MathML generation matches webbook rendering (visual parity)
2. PDF output renders math equations correctly (not as broken text/images)
3. The pipeline produces inspectable intermediate files for debugging
