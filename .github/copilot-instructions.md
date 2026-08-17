# GitHub Copilot custom instructions

These instructions apply to every Copilot coding-agent session in this
repository.

---

## CLI smoke-test after every fix or feature

After **every bug fix or new feature** is pushed, always end the response with
a **"How to verify on your server"** block that contains a minimal, copy-
paste-ready CLI command the user can run against their own files.  The block
must:

1. Use the real `pb-export` / `pb-postprocess-pdf` / `pb-extract-latex` entry
   points (not internal Python imports).
2. Reference a placeholder filename such as `dirty.html` or `export.html` so
   the user knows exactly which file to substitute.
3. Include a one-liner to confirm the fix — e.g. a `grep` or short `python3
   -c` snippet that prints the thing that was broken and is now correct.
4. Be enclosed in a fenced code block (` ```bash `).

### Template

```bash
# Verify <short description of the fix>
pb-export export.html \
  --format html \
  --output out.html

# Confirm the fix: <what to look for>
grep -o '<pattern>' out.html | head -5
```

---

## General agent style

* Make the **smallest possible correct change** — no unrelated refactors.
* Always run the existing test suite (`pytest`) before pushing.
* Never remove or weaken existing tests.
* Prefer ecosystem tools (linters, formatters, scaffolding) over manual edits.
