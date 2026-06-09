# MathML accessibility spike

This spike is the first milestone for the repository. Its purpose is to validate, with stakeholders and accessibility reviewers, that the planned MathJax-to-PDF pipeline is good enough before production implementation proceeds.

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

- [ ] Produce processed HTML with `<math>` elements from exported Pressbooks-style math images.
- [ ] Generate a PDF from the processed HTML.
- [ ] Run veraPDF and capture a report for accessibility review.
- [ ] Share the PDF with stakeholders for visual validation.
- [ ] Share the PDF with accessibility reviewers for assistive-technology validation.

## Usage

```bash
python -m pip install -r spike/requirements.txt
npm install --prefix spike
python spike/run_spike.py --output-dir spike/output
```

If `verapdf` is on your `PATH`, the spike runner will call it automatically after PDF generation.
