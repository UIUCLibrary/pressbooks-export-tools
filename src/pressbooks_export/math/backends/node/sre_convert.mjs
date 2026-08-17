/**
 * Convert one or many LaTeX expressions to plain-English spoken descriptions.
 *
 * Single-item mode (object input):
 *   stdin:  { "latex": "<expression>", "display": false }
 *   stdout: { "speech": "<spoken description>" }
 *           { "error": "<message>" }   (on error)
 *
 * Batch mode (array input):
 *   stdin:  [{ "latex": "<expression>", "display": false }, ...]
 *   stdout: [{ "speech": "..." }, ...]   (one result per input item;
 *            per-item errors use { "error": "<message>" })
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

/**
 * Convert a single { latex, display } item to { speech } or { error }.
 */
function convertOne(latex, display = false) {
  if (!latex) {
    return { error: 'Missing "latex" value in payload' };
  }
  try {
    const node = mjDocument.convert(latex, { display });
    const mathml = visitor.visitTree(node);
    const speech = SRE.toSpeech(mathml);
    return { speech };
  } catch (err) {
    return { error: err.message };
  }
}

try {
  const parsed = JSON.parse(input || '{}');

  if (Array.isArray(parsed)) {
    // Batch mode: process every item and return an array of results.
    const results = parsed.map(({ latex, display = false }) => convertOne(latex, display));
    process.stdout.write(JSON.stringify(results));
  } else {
    // Single-item mode (backward-compatible).
    const { latex, display = false } = parsed;
    const result = convertOne(latex, display);
    process.stdout.write(JSON.stringify(result));
    if (result.error) {
      process.exitCode = 1;
    }
  }
} catch (error) {
  process.stdout.write(JSON.stringify({ error: error.message }));
  process.exitCode = 1;
}
