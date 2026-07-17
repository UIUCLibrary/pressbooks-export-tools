#!/usr/bin/env python3
"""
apply-class-pdf-patch.py — whitespace-agnostic patcher for class-pdf.php

Replaces the single `$prince->convert_file_to_file(...)` call in Pressbooks'
inc/modules/export/prince/class-pdf.php with the full pressbooks-export-tools
pre/post-processing block.

Works regardless of tab vs space indentation and regardless of exact line
number, so it survives minor version divergence that defeats `patch -p1`.

Usage
-----
  python3 apply-class-pdf-patch.py <path-to-class-pdf.php> [options]

Options
  --pb-export PATH          Full path to pb-export binary
                            (default: /opt/pb-venv/bin/pb-export)
  --pb-postprocess PATH     Full path to pb-postprocess-pdf binary
                            (default: /opt/pb-venv/bin/pb-postprocess-pdf)
  --dry-run                 Print the modified file to stdout; do not write it
  --no-backup               Skip creating a .bak file
  -h / --help               Show this help

Examples
--------
  # Dry-run first to see what would change:
  python3 apply-class-pdf-patch.py class-pdf.php --dry-run | diff class-pdf.php -

  # Apply with default binary paths:
  sudo -u apache python3 apply-class-pdf-patch.py \
      /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php

  # Apply with custom binary paths:
  sudo -u apache python3 apply-class-pdf-patch.py \
      /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php \
      --pb-export /usr/local/bin/pb-export \
      --pb-postprocess /usr/local/bin/pb-postprocess-pdf
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# The insertion block.
#
# {I0} = indentation of the replaced line (matches original call depth).
# {I1} = one extra level in  (I0 + one indent unit).
# {I2} = two extra levels in, etc.
#
# Literal PHP braces are doubled ({{ / }}) to survive str.format().
# ---------------------------------------------------------------------------

BLOCK_TEMPLATE = """\
{I0}// =========================================================================
{I0}// pressbooks-export-tools: accessibility pre/post-processing
{I0}// Adjust the two paths below to match your install, then leave everything else.
{I0}// =========================================================================
{I0}$_pbet_bin     = '{pb_export}';
{I0}$_pbet_postbin = '{pb_postprocess}';

{I0}// ----- Step 1: fetch the book HTML into a secure temp file ---------------
{I0}$_pbet_src_html  = tempnam( sys_get_temp_dir(), 'pb_prince_src_' ) . '.html';
{I0}$_pbet_html_body = @file_get_contents( $this->url );

{I0}if ( $_pbet_html_body === false || $_pbet_html_body === '' ) {{
{I1}// Could not fetch HTML \u2014 fall back to the original Prince URL-based call.
{I1}error_log( '[pb-export-tools] Could not fetch HTML from ' . $this->url . '; using Prince URL fallback.' );
{I1}@unlink( $_pbet_src_html );
{I1}$retval = $prince->convert_file_to_file( $this->url, $this->outputPath, $msg );

{I0}}} else {{
{I1}file_put_contents( $_pbet_src_html, $_pbet_html_body );
{I1}unset( $_pbet_html_body );

{I1}// ----- Step 2: run pb-export to pre-process the HTML -----------------
{I1}$_pbet_processed   = tempnam( sys_get_temp_dir(), 'pb_prince_proc_' ) . '.html';
{I1}$_pbet_descriptors = [
{I2}0 => [ 'pipe', 'r' ],
{I2}1 => [ 'pipe', 'w' ],
{I2}2 => [ 'pipe', 'w' ],
{I1}];
{I1}$_pbet_cmd = [
{I2}$_pbet_bin,
{I2}'--format', 'html',
{I2}'--prince-preprocess',
{I2}// '--spoken-alt-text',  // uncomment after SRE is confirmed working
{I2}'--output', $_pbet_processed,
{I2}$_pbet_src_html,
{I1}];

{I1}$_pbet_proc = @proc_open( $_pbet_cmd, $_pbet_descriptors, $_pbet_pipes );

{I1}if ( is_resource( $_pbet_proc ) ) {{
{I2}fclose( $_pbet_pipes[0] );
{I2}fclose( $_pbet_pipes[1] );
{I2}$_pbet_stderr    = (string) stream_get_contents( $_pbet_pipes[2] );
{I2}fclose( $_pbet_pipes[2] );
{I2}$_pbet_exit_code = proc_close( $_pbet_proc );
{I1}}} else {{
{I2}$_pbet_exit_code = -1;
{I2}$_pbet_stderr    = 'proc_open failed to start pb-export';
{I1}}}

{I1}if ( $_pbet_exit_code === 0
{I2}&& file_exists( $_pbet_processed )
{I2}&& filesize( $_pbet_processed ) > 0
{I1}) {{
{I2}$_pbet_html_for_prince = $_pbet_processed;
{I2}error_log( '[pb-export-tools] HTML pre-processing succeeded.' );
{I1}}} else {{
{I2}error_log( '[pb-export-tools] pb-export pre-processing failed'
{I3}. ' (exit ' . $_pbet_exit_code . '): ' . $_pbet_stderr
{I3}. ' \u2014 falling back to unprocessed HTML.' );
{I2}@unlink( $_pbet_processed );
{I2}$_pbet_html_for_prince = $_pbet_src_html;
{I1}}}

{I1}// ----- Step 3: run Prince on the (possibly pre-processed) HTML -------
{I1}$retval = $prince->convert_file_to_file( $_pbet_html_for_prince, $this->outputPath, $msg );

{I1}// ----- Step 4: PDF/UA-2 post-processing ------------------------------
{I1}if ( file_exists( $this->outputPath ) && is_readable( $this->outputPath ) ) {{
{I2}$_pbet_post_cmd  = [ $_pbet_postbin, $this->outputPath ];
{I2}$_pbet_post_proc = @proc_open( $_pbet_post_cmd, $_pbet_descriptors, $_pbet_post_pipes );

{I2}if ( is_resource( $_pbet_post_proc ) ) {{
{I3}fclose( $_pbet_post_pipes[0] );
{I3}fclose( $_pbet_post_pipes[1] );
{I3}$_pbet_post_stderr = (string) stream_get_contents( $_pbet_post_pipes[2] );
{I3}fclose( $_pbet_post_pipes[2] );
{I3}$_pbet_post_exit   = proc_close( $_pbet_post_proc );

{I3}if ( $_pbet_post_exit === 0 ) {{
{I4}error_log( '[pb-export-tools] PDF/UA-2 post-processing complete: ' . $this->outputPath );
{I3}}} else {{
{I4}error_log( '[pb-export-tools] pb-postprocess-pdf failed'
{I5}. ' (exit ' . $_pbet_post_exit . '): ' . $_pbet_post_stderr );
{I3}}}
{I2}}} else {{
{I3}error_log( '[pb-export-tools] Could not start pb-postprocess-pdf; skipping.' );
{I2}}}
{I1}}}

{I1}// ----- Step 5: clean up temp files -----------------------------------
{I1}if ( isset( $_pbet_processed ) && $_pbet_html_for_prince !== $_pbet_processed ) {{
{I2}@unlink( $_pbet_processed );
{I1}}}
{I1}@unlink( $_pbet_src_html );
{I0}}}
{I0}// ========================================================================="""

# ---------------------------------------------------------------------------
# The target: only the first unconditional convert_file_to_file call.
# ---------------------------------------------------------------------------

TARGET_PATTERN = re.compile(
    r'^\s*\$retval\s*=\s*\$prince->convert_file_to_file\(\s*\$this->url,'
)

ALREADY_PATCHED_MARKER = "pressbooks-export-tools: accessibility pre/post-processing"


def detect_indent_unit(lines: list[str]) -> str:
    """
    Return the single-level indentation string used by the file ('\t' or spaces).

    Strategy: if any line starts with a tab, the file uses tabs.  Otherwise
    collect all positive indentation deltas between adjacent non-blank lines
    and return the smallest one (= one indent level).
    """
    for line in lines:
        if line.startswith("\t"):
            return "\t"

    # Space-indented file — find the smallest positive indent step.
    prev = 0
    min_delta = None
    for line in lines:
        stripped = line.lstrip(" ")
        if not stripped or stripped[0] in ("{", "}"):
            continue
        indent = len(line) - len(stripped)
        delta = indent - prev
        if delta > 0:
            min_delta = delta if min_delta is None else min(min_delta, delta)
        if indent > 0:
            prev = indent

    return " " * (min_delta or 4)


def build_block(i0: str, unit: str, pb_export: str, pb_postprocess: str) -> str:
    """Render BLOCK_TEMPLATE using the detected indentation."""
    return BLOCK_TEMPLATE.format(
        I0=i0,
        I1=i0 + unit,
        I2=i0 + unit * 2,
        I3=i0 + unit * 3,
        I4=i0 + unit * 4,
        I5=i0 + unit * 5,
        pb_export=pb_export,
        pb_postprocess=pb_postprocess,
    )


def apply_patch(
    php_file: Path,
    pb_export: str,
    pb_postprocess: str,
    dry_run: bool,
    no_backup: bool,
) -> int:
    """Read *php_file*, find the target line, replace it. Returns 0 on success."""
    original_text = php_file.read_text(encoding="utf-8")
    lines = original_text.splitlines(keepends=True)

    if ALREADY_PATCHED_MARKER in original_text:
        print(
            f"ERROR: {php_file} already contains the pressbooks-export-tools block. "
            "Aborting to avoid double-patching.",
            file=sys.stderr,
        )
        return 2

    target_idx: int | None = None
    for i, line in enumerate(lines):
        if TARGET_PATTERN.match(line):
            target_idx = i
            break

    if target_idx is None:
        print(
            "ERROR: Could not find the target line:\n"
            "  $retval = $prince->convert_file_to_file( $this->url, ...\n"
            f"in {php_file}.\n"
            "Verify this is the correct file and it has not already been modified.",
            file=sys.stderr,
        )
        return 1

    target_line = lines[target_idx]
    # Leading whitespace of the original call — becomes I0 in the block.
    i0 = target_line[: len(target_line) - len(target_line.lstrip())]
    unit = detect_indent_unit(lines)

    print(
        f"Target at line {target_idx + 1}  |  "
        f"i0={repr(i0)}  unit={repr(unit)}",
        file=sys.stderr,
    )

    block = build_block(i0, unit, pb_export, pb_postprocess)
    new_lines = lines[:target_idx] + [block + "\n"] + lines[target_idx + 1:]
    new_text = "".join(new_lines)

    if dry_run:
        sys.stdout.write(new_text)
        return 0

    if not no_backup:
        backup = php_file.with_suffix(php_file.suffix + ".bak")
        shutil.copy2(php_file, backup)
        print(f"Backup → {backup}", file=sys.stderr)

    php_file.write_text(new_text, encoding="utf-8")
    print(f"Written → {php_file}", file=sys.stderr)

    result = subprocess.run(
        ["php", "-l", str(php_file)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("PHP syntax check FAILED:\n" + result.stdout + result.stderr, file=sys.stderr)
        if not no_backup:
            shutil.copy2(backup, php_file)
            print(f"Restored backup from {backup}", file=sys.stderr)
        return 3

    print(result.stdout.strip(), file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("php_file", type=Path, help="Path to class-pdf.php")
    parser.add_argument(
        "--pb-export",
        default="/opt/pb-venv/bin/pb-export",
        metavar="PATH",
        help="Full path to pb-export (default: /opt/pb-venv/bin/pb-export)",
    )
    parser.add_argument(
        "--pb-postprocess",
        default="/opt/pb-venv/bin/pb-postprocess-pdf",
        metavar="PATH",
        help="Full path to pb-postprocess-pdf (default: /opt/pb-venv/bin/pb-postprocess-pdf)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print modified file to stdout without writing",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating a .bak file",
    )
    args = parser.parse_args()

    if not args.php_file.is_file():
        print(f"ERROR: {args.php_file} does not exist or is not a file.", file=sys.stderr)
        return 1

    return apply_patch(
        php_file=args.php_file,
        pb_export=args.pb_export,
        pb_postprocess=args.pb_postprocess,
        dry_run=args.dry_run,
        no_backup=args.no_backup,
    )


if __name__ == "__main__":
    sys.exit(main())
