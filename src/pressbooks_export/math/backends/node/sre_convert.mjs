/**
 * Convert a LaTeX expression to a plain-English spoken description.
 *
 * Reads a JSON object from stdin:
 *   { "latex": "<expression>", "display": false }
 *
 * Writes a JSON object to stdout:
 *   { "speech": "<spoken description>" }
 *
 * On error:
 *   { "error": "<message>" }
 *
 * Pipeline: LaTeX → MathML (MathJax) → spoken English (Speech Rule Engine).
 */

import { mathjax } from 'mathjax-full/js/mathjax.js';
import { TeX } from 'mathjax-full/js/input/tex.js';
import { liteAdaptor } from 'mathjax-full/js/adaptors/liteAdaptor.js';
import { RegisterHTMLHandler } from 'mathjax-full/js/handlers/html.js';
import { AllPackages } from 'mathjax-full/js/input/tex/AllPackages.js';
import { SerializedMmlVisitor } from 'mathjax-full/js/core/MmlTree/SerializedMmlVisitor.js';
import SRE from 'speech-rule-engine';

// ── MathJax setup ────────────────────────────────────────────────────────────
const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const tex = new TeX({ packages: AllPackages.filter((name) => name !== 'bussproofs') });
const mjDocument = mathjax.document('', { InputJax: tex });
const visitor = new SerializedMmlVisitor(mjDocument.mmlFactory);

// ── SRE setup ────────────────────────────────────────────────────────────────
// engineReady() resolves once SRE has loaded its locale data.
await SRE.engineReady();

// ── Read stdin ───────────────────────────────────────────────────────────────
let input = '';
for await (const chunk of process.stdin) {
  input += chunk;
}

try {
  const { latex, display = false } = JSON.parse(input || '{}');
  if (!latex) {
    throw new Error('Missing "latex" value in stdin payload');
  }

  // LaTeX → MathML
  const node = mjDocument.convert(latex, { display });
  const mathml = visitor.visitTree(node);

  // MathML → spoken English
  const speech = SRE.toSpeech(mathml);

  process.stdout.write(JSON.stringify({ speech }));
} catch (error) {
  process.stdout.write(JSON.stringify({ error: error.message }));
  process.exitCode = 1;
}
