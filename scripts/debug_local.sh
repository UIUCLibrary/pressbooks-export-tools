#!/usr/bin/env bash
# debug_local.sh — reproduce the WordPress plugin's pb-export pipeline locally.
#
# Usage:
#   ./scripts/debug_local.sh [dirty.html] [clean.html]
#
# Defaults:
#   dirty.html  →  example_documents/dirty.html
#   clean.html  →  /tmp/pb-debug-clean.html
#
# To test against a real Pressbooks export, copy the server's dirty.html here:
#   scp user@server:/var/www/html/wp-content/pb-export-debug/dirty.html \
#       example_documents/dirty.html
# (dirty.html is gitignored so large real exports won't be committed accidentally)
#
# The script mirrors the exact command the WordPress plugin runs in Step 2, so
# any Python traceback will be printed in full and exit code checked.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIRTY="${1:-$REPO_ROOT/example_documents/dirty.html}"
CLEAN="${2:-/tmp/pb-debug-clean.html}"

if [[ ! -f "$DIRTY" ]]; then
  echo "ERROR: dirty.html not found at $DIRTY"
  echo
  echo "Provide a Pressbooks HTML export as the first argument, or copy one to:"
  echo "  $REPO_ROOT/example_documents/dirty.html"
  exit 1
fi

# Resolve pb-export: prefer the venv the server uses, fall back to PATH.
PB_EXPORT="${PB_EXPORT:-$(command -v pb-export 2>/dev/null || true)}"
if [[ -z "$PB_EXPORT" ]]; then
  echo "ERROR: pb-export not found. Activate your venv or set PB_EXPORT=/path/to/pb-export"
  exit 1
fi

echo "── debug_local.sh ──────────────────────────────────────────"
echo "dirty  : $DIRTY ($(wc -c < "$DIRTY") bytes)"
echo "clean  : $CLEAN"
echo "pb-export: $PB_EXPORT"
echo "python : $(python3 --version 2>&1)"
echo "────────────────────────────────────────────────────────────"
echo

set -x
"$PB_EXPORT" \
  --format html \
  --prince-preprocess \
  --output "$CLEAN" \
  "$DIRTY"
{ set +x; } 2>/dev/null

echo
echo "── done ─────────────────────────────────────────────────────"
echo "Output: $CLEAN ($(wc -c < "$CLEAN") bytes)"
