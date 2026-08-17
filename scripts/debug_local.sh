#!/usr/bin/env bash
# debug_local.sh — reproduce the WordPress plugin's pb-export pipeline locally.
#
# Usage:
#   ./scripts/debug_local.sh [dirty.html] [clean.html] [output.pdf]
#
# Defaults:
#   dirty.html  →  example_documents/dirty.html
#   clean.html  →  /tmp/pb-debug-clean.html
#   output.pdf  →  /tmp/pb-debug-output.pdf  (only tested if it already exists)
#
# To grab the real files from the server in one go:
#   SERVER=user@your-server ./scripts/debug_local.sh
# or manually:
#   scp user@server:/var/www/html/wp-content/pb-export-debug/dirty.html \
#       example_documents/dirty.html
#   scp user@server:/var/www/html/wp-content/uploads/sites/.../exports/Book.pdf \
#       /tmp/pb-debug-output.pdf
#
# dirty.html is gitignored so large real exports won't be committed accidentally.
#
# The script mirrors the exact commands the WordPress plugin runs (Steps 2 & 4),
# printing full Python tracebacks so bugs can be reproduced and fixed locally.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIRTY="${1:-$REPO_ROOT/example_documents/dirty.html}"
CLEAN="${2:-/tmp/pb-debug-clean.html}"
PDF="${3:-/tmp/pb-debug-output.pdf}"

# ── optional: fetch files from the server automatically ──────────────────────
if [[ -n "${SERVER:-}" && ! -f "$DIRTY" ]]; then
  echo "Fetching dirty.html from $SERVER …"
  scp "$SERVER:/var/www/html/wp-content/pb-export-debug/dirty.html" "$DIRTY"
fi

if [[ ! -f "$DIRTY" ]]; then
  echo "ERROR: dirty.html not found at $DIRTY"
  echo
  echo "Options:"
  echo "  1. Set SERVER=user@your-server and re-run to fetch automatically."
  echo "  2. Copy manually:"
  echo "     scp user@server:/var/www/html/wp-content/pb-export-debug/dirty.html \\"
  echo "         $DIRTY"
  exit 1
fi

# ── resolve tool paths ────────────────────────────────────────────────────────
PB_EXPORT="${PB_EXPORT:-$(command -v pb-export 2>/dev/null || true)}"
if [[ -z "$PB_EXPORT" ]]; then
  echo "ERROR: pb-export not found. Activate your venv or set PB_EXPORT=/path/to/pb-export"
  exit 1
fi

PB_POSTPROC="${PB_POSTPROC:-$(command -v pb-postprocess-pdf 2>/dev/null || true)}"

echo "── debug_local.sh ──────────────────────────────────────────"
echo "dirty    : $DIRTY ($(wc -c < "$DIRTY") bytes)"
echo "clean    : $CLEAN"
echo "pdf      : $PDF"
echo "pb-export: $PB_EXPORT"
echo "pb-postproc: ${PB_POSTPROC:-not found}"
echo "python   : $(python3 --version 2>&1)"
echo "────────────────────────────────────────────────────────────"
echo

# ── Step 2: pb-export (HTML processing) ──────────────────────────────────────
echo "==> Step 2: pb-export --format html --prince-preprocess"
set -x
"$PB_EXPORT" \
  --format html \
  --prince-preprocess \
  --output "$CLEAN" \
  "$DIRTY"
{ set +x; } 2>/dev/null
echo "Step 2 OK: $(wc -c < "$CLEAN") bytes written to $CLEAN"
echo

# ── Step 4: pb-postprocess-pdf (only if a PDF exists to test against) ────────
if [[ -f "$PDF" ]]; then
  if [[ -z "${PB_POSTPROC:-}" ]]; then
    echo "WARNING: pb-postprocess-pdf not found on PATH; skipping Step 4."
    echo "  Install with: pip install 'pressbooks-export-tools[pdf]'"
  else
    echo "==> Step 4: pb-postprocess-pdf"
    set -x
    "$PB_POSTPROC" "$PDF"
    { set +x; } 2>/dev/null
    echo "Step 4 OK"
  fi
else
  echo "(Skipping Step 4: no PDF at $PDF)"
  echo " To test Step 4, copy a Prince-generated PDF there or pass it as \$3."
fi

echo
echo "── done ─────────────────────────────────────────────────────"
