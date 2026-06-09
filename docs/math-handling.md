# Math handling notes

## Terminology

- **Webbook**: the live Pressbooks browser experience where MathJax renders equations as MathML.
- **HTML export**: the static export where equations are often represented as images with LaTeX stored in `alt` text.

## Backend priority

1. **MathJax for Node.js**: primary backend because it matches the webbook rendering engine.
2. **latex2mathml**: pure-Python fallback for constrained environments.

## Accessibility spike focus

The spike validates whether replacing exported math images with MathML is sufficient for downstream PDF generation to meet stakeholder and accessibility-review expectations.
