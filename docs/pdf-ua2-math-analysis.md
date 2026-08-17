# PDF/UA-2 Math Compliance Analysis

## Executive Summary

**Recommendation: Use `luamml` for automatic MathML generation during LuaLaTeX compilation instead of the proposed Lua filter + sidecar files approach.**

This eliminates the need for:
- Custom Pandoc Lua filters
- Per-formula `.mml` sidecar files
- Complex pipeline to preserve MathML through Pandoc
- Manual `\tagpdfassocfile{}` injection

## The Core Problem

### What Pandoc Does

When Pandoc reads HTML containing MathML (`<math>` elements), it:
1. Converts MathML → LaTeX source (using tex-math library)
2. Stores only the LaTeX in its AST: `Math MathType Text`
3. **Discards the original MathML entirely**

There is no place in Pandoc's data model to preserve MathML alongside LaTeX. The `Math` inline stores only the LaTeX string.

### What PDF/UA-2 Requires

For PDF/UA-2 compliance, each Formula structure element should have:
- MathML as an Associated File (AF entry)
- Optionally, LaTeX source as another AF

The current pipeline loses MathML before it reaches the PDF generation step.

## Available Approaches

### Approach 1: luamml (RECOMMENDED)

**How it works**: `luamml` is a LaTeX package (included in TeX Live 2025+) that automatically converts LaTeX math to MathML during LuaLaTeX compilation.

**Usage**:
```latex
\DocumentMetadata{
  lang=en,
  pdfversion=2.0,
  pdfstandard=ua-2,
  tagging=on,
  testphase=math
}
\documentclass{article}
\usepackage{unicode-math}
\begin{document}
\[ E = mc^2 \]
\end{document}
```

With `tagging=on` and `testphase=math`, luamml automatically:
1. Converts each math expression to MathML
2. Embeds MathML as Associated Files on Formula structure elements
3. Handles the PDF/UA-2 tagging requirements

**Pros**:
- Zero changes to the Pressbooks pipeline
- No Pandoc Lua filters needed
- No sidecar files needed
- No MathML preservation logic needed
- Uses the same LaTeX math Pandoc already produces
- LaTeX3 team actively maintains this
- All arxiv-tagged examples use this approach

**Cons**:
- Requires TeX Live 2025+ (or `lualatex-dev`)
- luamml conversion may differ slightly from MathJax

**Pipeline Change**:
```
Current:
  Pressbooks HTML → MathJax → MathML HTML → Pandoc → LaTeX → LuaLaTeX → PDF

New (with luamml):
  Pressbooks HTML → MathJax → MathML HTML → Pandoc → LaTeX → lualatex-dev → PDF/UA-2
                                                              (with \DocumentMetadata)
```

### Approach 2: External MathML Injection

**How it works**: Pre-generate MathML and store in a lookup file. The LaTeX tagging system reads this file during compilation.

This is the arxiv approach for cases where externally-generated MathML (from LaTeXML) needs to be used instead of luamml-generated MathML.

**Files required** (from arxiv example):
- `document-body.tex` - The document content
- `document-mathml.html` - HTML file containing:
  - For each formula: LaTeX source, MD5 hash, and MathML
  - LaTeX3 tagging reads this and matches formulas by hash

**Usage**:
```latex
\DocumentMetadata{
  lang=en,
  pdfversion=2.0,
  pdfstandard=ua-2,
  pdfstandard=a-4f,
  tagging-setup={math/mathml/luamml/load=false},  % Don't use luamml
  uncompress
}
```

**Pros**:
- Preserves exact MathJax-generated MathML (semantic parity with webbook)
- Control over MathML quality/annotations

**Cons**:
- Requires generating the mathml.html lookup file
- More complex pipeline
- Need to match formulas by hash (fragile if LaTeX normalization differs)

### Approach 3: Lua Filter + Sidecar Files (Originally Proposed)

**How it works**: Custom Pandoc Lua filter intercepts Math AST nodes, recreates MathML, writes sidecar files, injects LaTeX macros.

**Why it's complex**:
1. Must recreate MathML from LaTeX (Pandoc discards original)
2. Must write `.mml` files for each formula
3. Must inject `\tagpdfassocfile{}` macros into LaTeX output
4. Must coordinate file naming and paths
5. Duplicates work that luamml already does

**Verdict**: This approach solves the wrong problem. The issue isn't "how to inject MathML into LaTeX" — it's "how to get MathML into the PDF". luamml already solves this.

### Approach 4: Bypass Pandoc

**How it works**: Write a custom HTML → LaTeX converter that preserves MathML metadata.

**Why it's overkill**:
- Pandoc handles HTML → LaTeX well
- The only issue is MathML preservation, which luamml solves differently

## Detailed Recommendation

### Primary Strategy: Use luamml

**Step 1: Update PDF generation to use DocumentMetadata**

Modify `src/pressbooks_export/converters/pdf.py`:

```python
# Generate LaTeX with Pandoc
pandoc_result = subprocess.run([
    pandoc_binary, str(input_path), "-o", str(tex_path),
    "--standalone"
], capture_output=True, text=True)

# Inject DocumentMetadata at the beginning
tex_content = tex_path.read_text()
tex_content = inject_document_metadata(tex_content)
tex_path.write_text(tex_content)

# Compile with lualatex-dev
subprocess.run([
    "lualatex-dev", "-interaction=nonstopmode", str(tex_path)
], cwd=tex_path.parent)
```

**Step 2: Create DocumentMetadata injection**

```python
DOCUMENT_METADATA = r"""
\DocumentMetadata{
  lang=en,
  pdfversion=2.0,
  pdfstandard=ua-2,
  tagging=on
}
"""

def inject_document_metadata(tex_content: str) -> str:
    """Insert \DocumentMetadata before \documentclass."""
    # Must appear before \documentclass
    return tex_content.replace(
        r"\documentclass",
        DOCUMENT_METADATA + r"\documentclass"
    )
```

**Step 3: Add unicode-math package**

Modify Pandoc template or post-process to add:
```latex
\usepackage{unicode-math}
```

### Fallback Strategy: External MathML (if luamml quality insufficient)

If luamml-generated MathML doesn't match MathJax quality closely enough:

1. Keep MathML from MathJax step (we already have it)
2. Write to `document-mathml.html` in the LaTeX3 format
3. Use `tagging-setup={math/mathml/luamml/load=false}`
4. Let LaTeX3 tagging read from the external file

This requires:
- Writing the MathML lookup file generator
- Understanding the MD5 hash matching (formula identification)

## Implementation Plan

### Phase 1: Validate luamml Approach (Spike)

1. Modify `spike/run_spike.py` to:
   - Generate LaTeX with Pandoc
   - Inject `\DocumentMetadata{tagging=on, pdfstandard=ua-2}`
   - Add `\usepackage{unicode-math}`
   - Compile with `lualatex-dev`

2. Validate with veraPDF that the output is PDF/UA-2 compliant

3. Test with NVDA + MathCAT to verify screen reader support

### Phase 2: Evaluate MathML Quality

Compare:
- MathJax-generated MathML (what we produce in Step 1)
- luamml-generated MathML (what ends up in PDF)

If they're semantically equivalent, stick with luamml.
If MathJax produces better/different MathML, implement external injection.

### Phase 3: Production Implementation

1. Update `PandocLuaLatexPdfConverter`:
   - Two-step: Pandoc → LaTeX, then inject metadata, then compile
   - Require `lualatex-dev` or TeX Live 2025+

2. Add configuration options:
   - PDF version (2.0 for UA-2)
   - PDF standards (ua-2, a-4f)
   - Language

3. Update documentation

## Requirements

### Software Requirements

| Software | Version | Notes |
|----------|---------|-------|
| TeX Live | 2025+ | Or use `lualatex-dev` from TL 2024 |
| Pandoc | Current | For HTML → LaTeX conversion |
| veraPDF | Current | For PDF/UA-2 validation |

### New Files/Components

With the luamml approach, **minimal new code is needed**:

1. **No new Python modules** - Just modify `pdf.py`
2. **No Lua filters** - luamml handles everything
3. **No sidecar file management** - Associated files are automatic
4. **One small function**: `inject_document_metadata()`

### Pipeline Changes

```
BEFORE:
  HTML with MathML → Pandoc → LaTeX → lualatex → PDF
  (MathML lost)

AFTER:
  HTML with MathML → Pandoc → LaTeX → inject_metadata → lualatex-dev → PDF/UA-2
  (luamml regenerates MathML from LaTeX during compilation)
```

## Risks and Mitigations

### Risk 1: luamml MathML differs from MathJax

**Likelihood**: Medium  
**Impact**: Low to Medium  
**Mitigation**: Both convert LaTeX → MathML. Differences should be cosmetic, not semantic. Test with screen readers to verify.

### Risk 2: TeX Live 2025+ availability

**Likelihood**: Low (TL 2025 released April 2025)  
**Impact**: Medium  
**Mitigation**: Use `lualatex-dev` on older installations, or provide Docker image with TL 2025.

### Risk 3: Complex LaTeX expressions fail

**Likelihood**: Low  
**Impact**: Medium  
**Mitigation**: The LaTeX3 team has tested extensively. Unsupported constructs can be documented and avoided.

## Open Questions

1. **Does MathJax-generated MathML have features luamml doesn't produce?**
   - MathJax may add `intent` attributes for better accessibility
   - Testing needed to evaluate importance

2. **What happens with very complex aligned equations?**
   - LaTeXML has special handling for `align` environments
   - luamml handles these via mtable
   - May need to compare output quality

3. **Is PDF/A-4f also required, or just PDF/UA-2?**
   - PDF/A-4f is for archival; adds AF embedding requirements
   - Can be enabled with `pdfstandard=a-4f` in DocumentMetadata

## Approach 5: Direct HTML → PDF with MathML Preservation

### Motivation

Since our pipeline already has HTML with MathML (`<math>` elements), an alternative
is to skip the LaTeX intermediate entirely and convert HTML directly to a tagged
PDF, writing a plugin or post-processor that embeds the MathML as Associated Files
on Formula structure elements.

### Tool Survey (June 2025)

| Tool | MathML Visual | Tagged PDF | PDF/UA-2 | Formula→AF(MathML) | Open Source | Viable? |
|---|---|---|---|---|---|---|
| **WeasyPrint** | ❌ | ✅ Partial | ✅ Claimed | ❌ | ✅ Python/AGPL | ❌ No MathML rendering |
| **Prince XML** | ✅ MathML 3.0 | ✅ | ❓ | ❓ | ❌ ~$5k/server | ❓ Needs testing |
| **Paged.js + Chrome** | ✅ (Chrome 109+) | ⚠️ Experimental | ❌ | ❌ | ✅ | ❌ Not conformant |
| **wkhtmltopdf** | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ Archived/dead |
| **Typst** | N/A (own format) | ✅ | ✅ | N/A | ✅ Rust | ❌ No HTML input |
| **PDFreactor** | ✅ | ✅ | ❓ | ❓ | ❌ Commercial | ❓ Needs testing |
| **Antenna House** | ✅ | ✅ | ✅ likely | ❓ Likely | ❌ Commercial | ❓ Needs testing |
| **LuaLaTeX + luamml** | ✅ Excellent | ✅ | ✅ Confirmed | ✅ **Yes** | ✅ TeX/MIT | ✅ **Best option** |

### WeasyPrint Plugin Path

WeasyPrint is the only open-source Python HTML→PDF tool with PDF/UA-2 support
(via `pdfua.py`), but it has two blockers:

1. **No MathML rendering** — Issue [#59](https://github.com/Kozea/WeasyPrint/issues/59)
   has been open since 2013 with no plans to fix.
2. **No Formula tag** — `_get_pdf_tag()` in `tags.py` maps `<math>` to `NonStruct`.
   A 2-line patch (`'math': 'Formula'`) would fix the tag, but the visual rendering
   gap remains.
3. **No AF injection API** — WeasyPrint has no plugin hooks for the tag-tree
   construction phase. Injecting per-element `AF` entries requires forking
   `add_tags()` (~200–400 lines of work).

A hybrid approach (WeasyPrint renders → pikepdf injects AF entries) is technically
feasible but still cannot render the math visually. You would need to pre-render
equations as SVG/images and use those as the visual representation while attaching
MathML via AF — a fragile and complex pipeline.

### pikepdf Post-Processing Path

For any tool that produces Formula structure elements but omits MathML AF entries,
pikepdf can inject them post-hoc:

```python
import pikepdf
from pikepdf import Dictionary, Array, Name, Stream, String

with pikepdf.Pdf.open("input.pdf") as pdf:
    # Navigate to Formula StructElems via StructTreeRoot
    formula_elem = ...
    # Create embedded MathML stream
    mml_data = b"<math xmlns='http://www.w3.org/1998/Math/MathML'>...</math>"
    ef_stream = pdf.make_stream(mml_data)
    ef_stream[Name.Subtype] = Name("/application#2Fmathml+xml")
    # Create filespec and attach AF
    filespec = pdf.make_indirect(Dictionary(
        Type=Name.Filespec, F=String("formula.mml"),
        UF=String("formula.mml"), EF=Dictionary(F=ef_stream),
        AFRelationship=Name.Supplement
    ))
    formula_elem[Name.AF] = Array([filespec])
    pdf.save("output.pdf")
```

**Challenge**: Matching each PDF Formula element to its source MathML requires
either position-based mapping (fragile) or embedding identifiers during conversion.

### Screen Reader MathML Patterns

NVDA's source code (`nvaccess/nvda:source/NVDAObjects/IAccessible/adobeAcrobat.py`)
documents three ways MathML appears in tagged PDFs:

1. **Nested tags** — Each MathML element is a separate StructElem child of Formula
   (what luamml + `testphase=math` produces — visible as `<Formula> → <math> → <msup> → <mi>`)
2. **AF entry** — Formula tag with MathML as the value from an Associated File
3. **MSFT_MathML** — Custom Microsoft Office attribute on the Formula tag

Pattern 1 is the richest for accessibility and is what our pipeline now targets.

### Assessment

No open-source HTML→PDF tool currently produces PDF/UA-2 compliant output with
MathML embedded as Associated Files on Formula structure elements. The commercial
tools (Prince, PDFreactor, Antenna House) may support this but require direct
testing at ~$5k/server.

**The HTML→LaTeX→PDF path via Pandoc + LuaLaTeX + luamml remains the only
confirmed open-source solution** that produces all three requirements:
visual math rendering, PDF/UA-2 tagged structure, and MathML in the tag tree.

## Conclusion

The proposed Lua filter + sidecar approach is **unnecessary complexity**. The LaTeX3 tagging-project has already solved MathML embedding for PDF/UA-2. 

**Use luamml**. It:
- Requires minimal pipeline changes
- Has no custom filter maintenance burden
- Is maintained by the LaTeX core team
- Is the approach used by all LaTeX3 PDF/UA-2 examples
- Works automatically once `\DocumentMetadata{tagging=on, testphase=math}` is set

The `testphase=math` key in `\DocumentMetadata` is critical — without it, `tagging=on`
creates Formula structure elements but does **not** activate luamml for MathML
generation and AF embedding. This was the root cause of formulas appearing as
plain text instead of MathML in the tag tree.

The only open question is whether luamml-generated MathML is acceptable, or whether
MathJax MathML must be preserved. Start with luamml (simpler), fall back to
external injection (Approach 2) if needed.
