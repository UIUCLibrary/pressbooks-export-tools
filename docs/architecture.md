# Architecture overview

The scaffold keeps the math-processing path separate from output backends so the repository can evolve toward a plugin-friendly Pressbooks export implementation.

## Layers

1. **Detection**: locate Pressbooks math placeholders in exported HTML.
2. **Conversion**: normalize LaTeX-to-MathML conversion behind pluggable backends.
3. **Substitution**: replace math images with MathML in the DOM.
4. **Output backends**: hand the processed HTML to format-specific converters.

## Planned deployment path

The long-term target is a Pressbooks export option, likely surfaced by a Pressbooks plugin. This scaffold keeps the core transformation logic isolated so a future plugin can invoke it without re-implementing the pipeline.
