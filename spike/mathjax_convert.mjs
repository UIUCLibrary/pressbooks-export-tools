import { mathjax } from 'mathjax-full/js/mathjax.js';
import { TeX } from 'mathjax-full/js/input/tex.js';
import { liteAdaptor } from 'mathjax-full/js/adaptors/liteAdaptor.js';
import { RegisterHTMLHandler } from 'mathjax-full/js/handlers/html.js';
import { AllPackages } from 'mathjax-full/js/input/tex/AllPackages.js';
import { SerializedMmlVisitor } from 'mathjax-full/js/core/MmlTree/SerializedMmlVisitor.js';

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const tex = new TeX({ packages: AllPackages.filter((name) => name !== 'bussproofs') });
const document = mathjax.document('', { InputJax: tex });
const visitor = new SerializedMmlVisitor(document.mmlFactory);

let input = '';
for await (const chunk of process.stdin) {
  input += chunk;
}

try {
  const { latex, display = false } = JSON.parse(input || '{}');
  if (!latex) {
    throw new Error('Missing "latex" value in stdin payload');
  }
  const node = document.convert(latex, { display });
  process.stdout.write(JSON.stringify({ mathml: visitor.visitTree(node) }));
} catch (error) {
  process.stdout.write(JSON.stringify({ error: error.message }));
  process.exitCode = 1;
}
