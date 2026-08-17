import { mathjax } from 'mathjax-full/js/mathjax.js';
import { TeX } from 'mathjax-full/js/input/tex.js';
import { liteAdaptor } from 'mathjax-full/js/adaptors/liteAdaptor.js';
import { RegisterHTMLHandler } from 'mathjax-full/js/handlers/html.js';
import { AllPackages } from 'mathjax-full/js/input/tex/AllPackages.js';
import { SerializedMmlVisitor } from 'mathjax-full/js/core/MmlTree/SerializedMmlVisitor.js';

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const tex = new TeX({ packages: AllPackages.filter((name) => name !== 'bussproofs') });
const doc = mathjax.document('', { InputJax: tex });
const visitor = new SerializedMmlVisitor(doc.mmlFactory);

function convertOne(latex, display) {
  const node = doc.convert(latex, { display });
  return visitor.visitTree(node);
}

let input = '';
for await (const chunk of process.stdin) {
  input += chunk;
}

try {
  const payload = JSON.parse(input || '{}');

  // Batch mode: payload is an array of { latex, display } objects.
  // Returns an array of { mathml } or { error } results — one per input item.
  if (Array.isArray(payload)) {
    const results = payload.map(({ latex, display = false }) => {
      if (!latex) {
        return { error: 'Missing "latex" value' };
      }
      try {
        return { mathml: convertOne(latex, display) };
      } catch (err) {
        return { error: err.message };
      }
    });
    process.stdout.write(JSON.stringify(results));
  } else {
    // Single-item mode: payload is { latex, display }.
    const { latex, display = false } = payload;
    if (!latex) {
      throw new Error('Missing "latex" value in stdin payload');
    }
    process.stdout.write(JSON.stringify({ mathml: convertOne(latex, display) }));
  }
} catch (error) {
  process.stdout.write(JSON.stringify({ error: error.message }));
  process.exitCode = 1;
}
