# Pressbooks integration guide

This document describes how to wire `pressbooks-export-tools` into an existing
Pressbooks + Prince XML instance so that non-technical authors can click the
normal **Export → Print PDF (Prince)** button and automatically receive:

- math images tagged with `role="math"` (Prince `Formula` structure elements)
- spoken alt text replacing raw LaTeX on math images (optional; requires SRE)
- PDF/UA-2 metadata fixes (`DisplayDocTitle`, `pdfuaid:part=2` XMP)

Three approaches are documented here.  Start with **Option A** (drop-in file
copy) — it requires copying one pre-patched file and adjusting two paths.  Use
**Option B** (manual patch) if your Pressbooks version differs from ours and
the drop-in copy causes issues.  Move to **Option C** (mu-plugin) when you want
the logic to survive Pressbooks core updates.

> **MacGyver note** — this setup is intentionally provisional and targets a
> specific internal instance used for PDF generation and author training.  The
> approach is designed to be low-risk: every step has a fallback so that exports
> continue to work even when the Python tooling is unavailable.

---

## 1. Server prerequisites (all options)

All commands that follow must be run as (or be accessible to) the web-server
user — `www-data` on most Debian/Ubuntu installs.

### 1a. Install the Python package

```bash
# Clone the repo if you haven't already.
git clone https://github.com/UIUCLibrary/pressbooks-export-tools.git /opt/pressbooks-export-tools

# Install into a dedicated venv so the entry-point scripts end up in a
# predictable location (/opt/pb-venv/bin/).
python3 -m venv /opt/pb-venv
/opt/pb-venv/bin/pip install -e /opt/pressbooks-export-tools[pdf]
```

Confirm the two binaries exist and are executable:

```bash
ls -la /opt/pb-venv/bin/pb-export
ls -la /opt/pb-venv/bin/pb-postprocess-pdf
```

Verify they run as the web-server user:

```bash
sudo -u www-data /opt/pb-venv/bin/pb-export --help
sudo -u www-data /opt/pb-venv/bin/pb-postprocess-pdf --help
```

Both commands should print their help text.  If you see a permission error,
check that `www-data` can read `/opt/pb-venv/` and `/opt/pressbooks-export-tools/`.

### 1b. Enable WordPress debug logging

You need the PHP error log to verify the pipeline is running.  Add these lines
to `wp-config.php` if they are not already there:

```php
define( 'WP_DEBUG', true );
define( 'WP_DEBUG_LOG', true );   // writes to wp-content/debug.log
define( 'WP_DEBUG_DISPLAY', false );
```

### 1c. Node.js / Speech Rule Engine (optional — skip for now)

The `--spoken-alt-text` flag (plain-English descriptions instead of raw LaTeX
in alt text) requires Node.js ≥ 18.  Leave it disabled on first deployment;
add it once the baseline pipeline is confirmed working.

```bash
# Later, when you want spoken alt text:
npm install --prefix /opt/pressbooks-export-tools/src/pressbooks_export/math/backends/node
sudo -u www-data node /opt/pressbooks-export-tools/src/pressbooks_export/math/backends/node/sre.js x
```

---

## Digital PDF vs Print PDF

Pressbooks registers **two** separate Prince PDF export types:

| Export type | PHP class | Source file |
|---|---|---|
| Digital PDF (Prince) | `Pdf` | `class-pdf.php` |
| Print PDF (Prince) | `PdfPrint` | `class-pdfprint.php` (if present) |

Both classes contain the same `$prince->convert_file_to_file($this->url, …)`
call that must be replaced.  **If you only patch `class-pdf.php`, the
tools pipeline runs on digital PDF exports but is silently bypassed for print
PDF** (no `[pb-export-tools]` entries appear in the log for print exports).

Option A (drop-in copy) only covers `class-pdf.php`.  Use **Option B** (the
Python patch script pointed at the whole `prince/` directory) to patch all
applicable classes in one step — this is now the recommended approach.

---

## Option A — Drop-in file copy (digital PDF only)

`docs/class-pdf.php` in this repository is a fully pre-patched copy of
Pressbooks' `inc/modules/export/prince/class-pdf.php`.  It covers the
**digital PDF** export only.  If you also need to patch the print PDF class,
use Option B instead.

### A1. Adjust the two binary paths

Open `docs/class-pdf.php` and find the two lines marked `← full path to`:

```php
$_pbet_bin     = '/opt/pb-venv/bin/pb-export';          // ← full path to pb-export
$_pbet_postbin = '/opt/pb-venv/bin/pb-postprocess-pdf'; // ← full path to pb-postprocess-pdf
```

Update them to match your install if the binaries live somewhere else, then save.

### A2. Back up and copy

```bash
# Back up the original
cp /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php \
   /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php.bak

# Drop in the pre-patched copy
cp /opt/pressbooks-export-tools/docs/class-pdf.php \
   /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php
```

### A3. Verify syntax

```bash
php -l /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php
```

Expected output: `No syntax errors detected in ...`

### A4. Test an export

1. Log into Pressbooks and open any book.
2. Go to **Export** and click **Export your book** with **Digital PDF (Prince)** selected.
3. While it runs, tail the debug log in another terminal:
   ```bash
   tail -f /var/www/html/wp-content/debug.log | grep pb-export-tools
   ```
4. A successful run produces output like:
   ```
   [pb-export-tools] ── export start ──────────────────────────
   [pb-export-tools] source URL  : http://…/format/xhtml?timestamp=…
   [pb-export-tools] output PDF  : /var/www/html/wp-content/uploads/…pdf
   [pb-export-tools] debug dir   : /var/www/html/wp-content/pb-export-debug
   [pb-export-tools] pb-export   : /opt/pb-venv/bin/pb-export (found)
   [pb-export-tools] pb-postproc : /opt/pb-venv/bin/pb-postprocess-pdf (found)
   [pb-export-tools] Step 1: fetching HTML from …
   [pb-export-tools] Step 1 OK: fetched 123456 bytes.
   [pb-export-tools] Step 1: wrote dirty.html — 123456 bytes at …/dirty.html
   [pb-export-tools] Step 2: running pb-export on dirty.html → clean.html
   [pb-export-tools] Step 2: command: …
   [pb-export-tools] Step 2: pb-export exit=0
   [pb-export-tools] Step 2: clean.html exists=yes size=123789 bytes
   [pb-export-tools] Step 2 OK: using clean.html for Prince.
   [pb-export-tools] Step 3: running Prince on clean.html
   [pb-export-tools] Step 3: Prince retval=true pdf_size=987654 bytes at …
   [pb-export-tools] Step 4: running pb-postprocess-pdf on …
   [pb-export-tools] Step 4: pb-postprocess-pdf exit=0
   [pb-export-tools] Step 4 OK: PDF/UA-2 post-processing complete.
   [pb-export-tools] ── export end ────────────────────────────
   ```
5. After the export, inspect the staging files to debug any issue:
   ```bash
   ls -lh /var/www/html/wp-content/pb-export-debug/
   # dirty.html — raw HTML as fetched from Pressbooks (before pb-export)
   # clean.html — HTML after pb-export pre-processing (fed to Prince)
   ```

### A5. Rolling back

```bash
cp /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php.bak \
   /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php
```

> **Version note** — `docs/class-pdf.php` was generated against the Pressbooks
> `dev` branch at the time this repository was last updated.  If Pressbooks has
> received upstream changes to `class-pdf.php` since then, use Option B (the
> Python patch script) instead.

---

## Option B — Self-contained patch script (recommended for all installs)

Use this to patch both the digital PDF class and the print PDF class (if
present) in one step.  The script finds the target line by content rather than
by line number, so it survives minor version divergence that defeats `patch -p1`.
It detects tab vs space indentation automatically, backs up the originals, and
runs `php -l` to verify syntax.

### B1. Apply the patch with the Python script

**Point the script at the `prince/` directory** to patch every PHP file that
contains the target call (typically `class-pdf.php` for digital PDF and
`class-pdfprint.php` for print PDF):

```bash
# Dry-run first — lists patchable files and prints their patched content:
sudo -u www-data python3 /opt/pressbooks-export-tools/docs/apply-class-pdf-patch.py \
    /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/ \
    --dry-run

# Apply (creates .bak files and runs php -l for each file automatically):
sudo -u www-data python3 /opt/pressbooks-export-tools/docs/apply-class-pdf-patch.py \
    /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/
```

Expected stderr output on success (two files patched):

```
Found 2 patchable file(s) in …/prince/:
  class-pdf.php
  class-pdfprint.php

── Patching …/class-pdf.php ──
Target at line 147  |  i0='\t\t'  unit='\t'
Backup → …/class-pdf.php.bak
Written → …/class-pdf.php
No syntax errors detected in …/class-pdf.php

── Patching …/class-pdfprint.php ──
Target at line 89  |  i0='\t\t'  unit='\t'
Backup → …/class-pdfprint.php.bak
Written → …/class-pdfprint.php
No syntax errors detected in …/class-pdfprint.php
```

If your Pressbooks install only has `class-pdf.php` (no separate print class),
the script will report one file found and patch only that one.

To patch a single file instead of the whole directory:

```bash
sudo -u www-data python3 /opt/pressbooks-export-tools/docs/apply-class-pdf-patch.py \
    /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php
```

To roll back all patched files:

```bash
PRINCE=/var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince
for f in "$PRINCE"/*.php.bak; do cp "$f" "${f%.bak}"; done
```

### B2. Manual fallback (if you prefer not to run Python as apache)

Find the file:

```bash
find /var/www/html/wp-content/plugins/pressbooks \
     -name "class-pdf.php" \
     -path "*/prince/*"
```

Find the exact target line:

```bash
grep -n "convert_file_to_file" \
  /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php
```

You should see exactly one hit (the unconditional original call):

```
147:		$retval = $prince->convert_file_to_file( $this->url, $this->outputPath, $msg );
```

Back up the file:

```bash
cp /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php \
   /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php.bak
```

Open the file in your editor.  Find this **exact line** (it is the only call to
`convert_file_to_file` in the file):

```php
$retval = $prince->convert_file_to_file( $this->url, $this->outputPath, $msg );
```

**Delete that single line** and paste the following block in its place.
The only values you must adjust are the two binary paths at the top
(`$_pbet_bin` and `$_pbet_postbin`):

```php
// =========================================================================
// pressbooks-export-tools: accessibility pre/post-processing
// Adjust the two paths below to match your install, then leave everything else.
// =========================================================================
$_pbet_bin     = '/opt/pb-venv/bin/pb-export';          // ← full path to pb-export
$_pbet_postbin = '/opt/pb-venv/bin/pb-postprocess-pdf'; // ← full path to pb-postprocess-pdf

// Debug staging directory — all intermediate files land here so you can
// inspect them after an export.  www-data must be able to write to it.
$_pbet_debug_dir = WP_CONTENT_DIR . '/pb-export-debug';
if ( ! is_dir( $_pbet_debug_dir ) ) {
	mkdir( $_pbet_debug_dir, 0755, true );
}
$_pbet_dirty_html = $_pbet_debug_dir . '/dirty.html';   // raw HTML fetched from Pressbooks
$_pbet_clean_html = $_pbet_debug_dir . '/clean.html';   // HTML after pb-export processing

error_log( '[pb-export-tools] ── export start ──────────────────────────' );
error_log( '[pb-export-tools] source URL  : ' . $this->url );
error_log( '[pb-export-tools] output PDF  : ' . $this->outputPath );
error_log( '[pb-export-tools] debug dir   : ' . $_pbet_debug_dir );
error_log( '[pb-export-tools] pb-export   : ' . $_pbet_bin . ( is_executable( $_pbet_bin ) ? ' (found)' : ' (NOT FOUND)' ) );
error_log( '[pb-export-tools] pb-postproc : ' . $_pbet_postbin . ( is_executable( $_pbet_postbin ) ? ' (found)' : ' (NOT FOUND)' ) );

// ----- Step 1: fetch the book HTML ---------------------------------------
error_log( '[pb-export-tools] Step 1: fetching HTML from ' . $this->url );
$_pbet_html_body = @file_get_contents( $this->url );

if ( $_pbet_html_body === false || $_pbet_html_body === '' ) {
	error_log( '[pb-export-tools] Step 1 FAILED: could not fetch HTML — falling back to Prince URL call.' );
	$retval = $prince->convert_file_to_file( $this->url, $this->outputPath, $msg );

} else {
	error_log( '[pb-export-tools] Step 1 OK: fetched ' . strlen( $_pbet_html_body ) . ' bytes.' );

	// Fix bare & characters that would break XML parsing.
	$_pbet_html_body = preg_replace( '/&(?![a-zA-Z]{2,6};|#\d{2,5};)/', '&amp;', $_pbet_html_body );
	// Inject unique id="chapter-N" on every h1.chapter-title2 element.
	$_pbet_ch_counter = 0;
	$_pbet_html_body  = preg_replace_callback(
		'/<h1\s+class="chapter-title2">/',
		function ( $matches ) use ( &$_pbet_ch_counter ) {
			$_pbet_ch_counter++;
			return '<h1 class="chapter-title2" id="chapter-' . $_pbet_ch_counter . '">';
		},
		$_pbet_html_body
	);

	$_pbet_wrote = file_put_contents( $_pbet_dirty_html, $_pbet_html_body );
	unset( $_pbet_html_body );
	error_log( '[pb-export-tools] Step 1: wrote dirty.html — '
		. ( $_pbet_wrote !== false ? $_pbet_wrote . ' bytes at ' . $_pbet_dirty_html : 'WRITE FAILED' ) );

	// ----- Step 2: run pb-export to pre-process the HTML -----------------
	error_log( '[pb-export-tools] Step 2: running pb-export on dirty.html → clean.html' );

	// Remove stale clean.html from a previous run so a zero-byte file is
	// never mistaken for a successful output.
	@unlink( $_pbet_clean_html );

	$_pbet_descriptors = [
		0 => [ 'pipe', 'r' ],
		1 => [ 'pipe', 'w' ],
		2 => [ 'pipe', 'w' ],
	];
	$_pbet_cmd = [
		$_pbet_bin,
		'--format', 'html',
		'--prince-preprocess',
		// '--spoken-alt-text',  // uncomment after SRE is confirmed working
		'--output', $_pbet_clean_html,
		$_pbet_dirty_html,
	];
	error_log( '[pb-export-tools] Step 2: command: ' . implode( ' ', array_map( 'escapeshellarg', $_pbet_cmd ) ) );

	$_pbet_proc = @proc_open( $_pbet_cmd, $_pbet_descriptors, $_pbet_pipes );

	if ( is_resource( $_pbet_proc ) ) {
		fclose( $_pbet_pipes[0] );
		$_pbet_stdout    = (string) stream_get_contents( $_pbet_pipes[1] );
		fclose( $_pbet_pipes[1] );
		$_pbet_stderr    = (string) stream_get_contents( $_pbet_pipes[2] );
		fclose( $_pbet_pipes[2] );
		$_pbet_exit_code = proc_close( $_pbet_proc );
	} else {
		$_pbet_exit_code = -1;
		$_pbet_stdout    = '';
		$_pbet_stderr    = 'proc_open failed — check disable_functions in php.ini';
	}

	error_log( '[pb-export-tools] Step 2: pb-export exit=' . $_pbet_exit_code );
	if ( $_pbet_stdout !== '' ) {
		error_log( '[pb-export-tools] Step 2: stdout: ' . $_pbet_stdout );
	}
	if ( $_pbet_stderr !== '' ) {
		error_log( '[pb-export-tools] Step 2: stderr: ' . $_pbet_stderr );
	}

	$_pbet_clean_exists = file_exists( $_pbet_clean_html );
	$_pbet_clean_size   = $_pbet_clean_exists ? filesize( $_pbet_clean_html ) : 0;
	error_log( '[pb-export-tools] Step 2: clean.html exists=' . ( $_pbet_clean_exists ? 'yes' : 'no' )
		. ' size=' . $_pbet_clean_size . ' bytes' );

	if ( $_pbet_exit_code === 0 && $_pbet_clean_exists && $_pbet_clean_size > 0 ) {
		$_pbet_html_for_prince = $_pbet_clean_html;
		error_log( '[pb-export-tools] Step 2 OK: using clean.html for Prince.' );
	} else {
		error_log( '[pb-export-tools] Step 2 FAILED: falling back to dirty.html for Prince.' );
		$_pbet_html_for_prince = $_pbet_dirty_html;
	}

	// ----- Step 3: run Prince on the (possibly pre-processed) HTML -------
	error_log( '[pb-export-tools] Step 3: running Prince on ' . basename( $_pbet_html_for_prince ) );
	$retval = $prince->convert_file_to_file( $_pbet_html_for_prince, $this->outputPath, $msg );
	$_pbet_pdf_size = file_exists( $this->outputPath ) ? filesize( $this->outputPath ) : 0;
	error_log( '[pb-export-tools] Step 3: Prince retval=' . var_export( $retval, true )
		. ' pdf_size=' . $_pbet_pdf_size . ' bytes at ' . $this->outputPath );

	// ----- Step 4: PDF/UA-2 post-processing ------------------------------
	if ( file_exists( $this->outputPath ) && $_pbet_pdf_size > 0 ) {
		error_log( '[pb-export-tools] Step 4: running pb-postprocess-pdf on ' . $this->outputPath );
		$_pbet_post_cmd  = [ $_pbet_postbin, $this->outputPath ];
		$_pbet_post_proc = @proc_open( $_pbet_post_cmd, $_pbet_descriptors, $_pbet_post_pipes );

		if ( is_resource( $_pbet_post_proc ) ) {
			fclose( $_pbet_post_pipes[0] );
			$_pbet_post_stdout = (string) stream_get_contents( $_pbet_post_pipes[1] );
			fclose( $_pbet_post_pipes[1] );
			$_pbet_post_stderr = (string) stream_get_contents( $_pbet_post_pipes[2] );
			fclose( $_pbet_post_pipes[2] );
			$_pbet_post_exit   = proc_close( $_pbet_post_proc );

			error_log( '[pb-export-tools] Step 4: pb-postprocess-pdf exit=' . $_pbet_post_exit );
			if ( $_pbet_post_stdout !== '' ) {
				error_log( '[pb-export-tools] Step 4: stdout: ' . $_pbet_post_stdout );
			}
			if ( $_pbet_post_stderr !== '' ) {
				error_log( '[pb-export-tools] Step 4: stderr: ' . $_pbet_post_stderr );
			}
			if ( $_pbet_post_exit === 0 ) {
				error_log( '[pb-export-tools] Step 4 OK: PDF/UA-2 post-processing complete.' );
			} else {
				error_log( '[pb-export-tools] Step 4 FAILED: pb-postprocess-pdf did not succeed.' );
			}
		} else {
			error_log( '[pb-export-tools] Step 4 FAILED: could not start pb-postprocess-pdf.' );
		}
	} else {
		error_log( '[pb-export-tools] Step 4 SKIPPED: no PDF to post-process (Prince produced nothing).' );
	}

	error_log( '[pb-export-tools] ── export end ────────────────────────────' );
	// Staging files (dirty.html, clean.html) are intentionally kept for inspection.
}
// =========================================================================
```

### B3. Verify the file has no PHP syntax errors

> **Note:** the Python script (B1) runs this automatically.  Only needed after a
> manual edit (B2).

```bash
php -l /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php
```

Expected output: `No syntax errors detected in ...`

If you see a parse error, restore the backup (`cp class-pdf.php.bak class-pdf.php`) and check that you pasted the block cleanly without leaving the original line in place.

### B4. Test an export

1. Log into Pressbooks and open any book.
2. Go to **Export** and click **Export your book** with **Digital PDF (Prince)** selected.
3. While it runs, tail the debug log in another terminal:
   ```bash
   tail -f /var/www/html/wp-content/debug.log | grep pb-export-tools
   ```
4. A successful run produces step-by-step output (see A4 for the full example).
5. After the export you can inspect the staging files:
   ```bash
   ls -lh /var/www/html/wp-content/pb-export-debug/
   # dirty.html — raw HTML fetched from Pressbooks (before pb-export)
   # clean.html — HTML after pb-export pre-processing (fed to Prince)
   ```
6. Download the generated PDF and open it.  In Acrobat go to
   **File → Properties → Description** — the book title should appear in the
   title bar (DisplayDocTitle fix).

### B5. Enabling spoken alt text later

When Node.js and SRE are installed and verified, uncomment the one line in the
block above:

```php
// '--spoken-alt-text',  // uncomment after SRE is confirmed working
```

Change it to:

```php
'--spoken-alt-text',
```

No other changes needed.

### B6. Rolling back

To remove the hack entirely and restore original behaviour:

```bash
cp /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php.bak \
   /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php
```

---

## Option C — mu-plugin approach (survives Pressbooks updates)

Use this when Option A or B is confirmed working and you want the logic to live
outside Pressbooks core so it survives future `composer update` runs.

### C1. Install the mu-plugin

```bash
cp /opt/pressbooks-export-tools/mu-plugins/pb-export-postprocess.php \
   /var/www/html/wp-content/mu-plugins/
```

Must-use plugins load automatically — no activation step is needed.

### C2. Apply the minimal class-pdf.php patch

Replace the same `convert_file_to_file` line with this much shorter block
(all the logic now lives in the mu-plugin):

```php
// --- pressbooks-export-tools: fetch HTML to a temp file and pre-process --
$_pb_et_tmp_html = tempnam( sys_get_temp_dir(), 'pb_prince_src_' ) . '.html';
file_put_contents( $_pb_et_tmp_html, file_get_contents( $this->url ) );

$_pb_et_html_for_prince = apply_filters(
	'pb_export_tools_preprocess_html_path',
	$_pb_et_tmp_html,
);

// --- Prince conversion ---------------------------------------------------
$retval = $prince->convert_file_to_file( $_pb_et_html_for_prince, $this->outputPath, $msg );

// --- PDF post-processing and cleanup -------------------------------------
do_action( 'pb_export_tools_postprocess_pdf', $this->outputPath );
do_action( 'pb_export_tools_cleanup_temp_html', $_pb_et_html_for_prince, $_pb_et_tmp_html );
@unlink( $_pb_et_tmp_html );
```

### C3. Configure binary paths

Visit **Dashboard → Settings → PB Export Tools** and enter the full paths:

| Setting | Value |
|---|---|
| Enable post-processing | ✓ checked |
| Spoken alt text | leave unchecked initially |
| pb-export path | `/opt/pb-venv/bin/pb-export` |
| pb-postprocess-pdf path | `/opt/pb-venv/bin/pb-postprocess-pdf` |

Status banners on that page indicate whether the binaries were found.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Could not fetch HTML` in log | `$this->url` unreachable from CLI context | Check `allow_url_fopen` in `php.ini`; try `curl` from the shell as `www-data` |
| `proc_open failed` in log | `proc_open` disabled in `php.ini` | Check `disable_functions` in `php.ini`; remove `proc_open` from the list |
| `pb-export pre-processing failed (exit -1)` | Binary not found or not executable | Run `sudo -u www-data /opt/pb-venv/bin/pb-export --help`; check path in the code |
| Export works but PDFs look unchanged | Pre-processing ran but book has no math images | Confirm with a book that has LaTeX equations; check for `<img class="latex">` in source |
| Export broken after patch | Syntax error in pasted block | `php -l class-pdf.php`; restore backup |
| No log output at all | `WP_DEBUG_LOG` not enabled | Add `define('WP_DEBUG_LOG', true)` to `wp-config.php` |

---

## Future direction

Once the MacGyver phase proves out the pipeline:

- Submit the `apply_filters` / `do_action` call points as a pull request to
  Pressbooks upstream, so the core patch is no longer needed.
- Package the mu-plugin for distribution via the WordPress plugin directory or
  as a Composer dependency.
- Add a Pressbooks-native export format option so authors can select
  "Accessible PDF (Prince + export-tools)" from the export screen.

