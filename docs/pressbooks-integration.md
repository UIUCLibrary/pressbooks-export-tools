# Pressbooks integration guide

This document describes how to wire `pressbooks-export-tools` into an existing
Pressbooks + Prince XML instance so that non-technical authors can click the
normal **Export → Print PDF (Prince)** button and automatically receive:

- math images tagged with `role="math"` (Prince `Formula` structure elements)
- spoken alt text replacing raw LaTeX on math images (optional; requires SRE)
- PDF/UA-2 metadata fixes (`DisplayDocTitle`, `pdfuaid:part=2` XMP)

Two approaches are documented here.  Start with **Option A** (the self-contained
hack) — it requires editing one file and nothing else.  Move to **Option B**
(mu-plugin) when you want the logic to survive Pressbooks core updates.

> **MacGyver note** — this setup is intentionally provisional and targets a
> specific internal instance used for PDF generation and author training.  The
> approach is designed to be low-risk: every step has a fallback so that exports
> continue to work even when the Python tooling is unavailable.

---

## 1. Server prerequisites (both options)

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

## Option A — Self-contained hack (edit one file, no mu-plugin)

This is the fastest path.  All the logic lives inline inside `class-pdf.php`.

### A1. Locate the file and the line to replace

```bash
# Find the file (path varies by Pressbooks version and install layout).
find /var/www/html/wp-content/plugins/pressbooks \
     -name "class-pdf.php" \
     -path "*/prince/*"
```

Typical path:
```
/var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php
```

Find the exact line number of the `convert_file_to_file` call:

```bash
grep -n "convert_file_to_file" \
  /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php
```

You should see one hit, something like:

```
145:			$retval = $prince->convert_file_to_file( $this->url, $this->outputPath, $msg );
```

### A2. Back up the file

```bash
cp /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php \
   /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php.bak
```

### A3. Open the file and find the block to replace

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

// ----- Step 1: fetch the book HTML into a secure temp file ---------------
$_pbet_src_html  = tempnam( sys_get_temp_dir(), 'pb_prince_src_' ) . '.html';
$_pbet_html_body = @file_get_contents( $this->url );

if ( $_pbet_html_body === false || $_pbet_html_body === '' ) {
	// Could not fetch HTML — fall back to the original Prince URL-based call.
	error_log( '[pb-export-tools] Could not fetch HTML from ' . $this->url . '; using Prince URL fallback.' );
	@unlink( $_pbet_src_html );
	$retval = $prince->convert_file_to_file( $this->url, $this->outputPath, $msg );

} else {
	file_put_contents( $_pbet_src_html, $_pbet_html_body );
	unset( $_pbet_html_body );

	// ----- Step 2: run pb-export to pre-process the HTML -----------------
	$_pbet_processed   = tempnam( sys_get_temp_dir(), 'pb_prince_proc_' ) . '.html';
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
		'--output', $_pbet_processed,
		$_pbet_src_html,
	];

	$_pbet_proc = @proc_open( $_pbet_cmd, $_pbet_descriptors, $_pbet_pipes );

	if ( is_resource( $_pbet_proc ) ) {
		fclose( $_pbet_pipes[0] );
		fclose( $_pbet_pipes[1] );
		$_pbet_stderr    = (string) stream_get_contents( $_pbet_pipes[2] );
		fclose( $_pbet_pipes[2] );
		$_pbet_exit_code = proc_close( $_pbet_proc );
	} else {
		$_pbet_exit_code = -1;
		$_pbet_stderr    = 'proc_open failed to start pb-export';
	}

	if ( $_pbet_exit_code === 0
		&& file_exists( $_pbet_processed )
		&& filesize( $_pbet_processed ) > 0
	) {
		$_pbet_html_for_prince = $_pbet_processed;
		error_log( '[pb-export-tools] HTML pre-processing succeeded.' );
	} else {
		error_log( '[pb-export-tools] pb-export pre-processing failed'
			. ' (exit ' . $_pbet_exit_code . '): ' . $_pbet_stderr
			. ' — falling back to unprocessed HTML.' );
		@unlink( $_pbet_processed );
		$_pbet_html_for_prince = $_pbet_src_html;
	}

	// ----- Step 3: run Prince on the (possibly pre-processed) HTML -------
	$retval = $prince->convert_file_to_file( $_pbet_html_for_prince, $this->outputPath, $msg );

	// ----- Step 4: PDF/UA-2 post-processing ------------------------------
	if ( file_exists( $this->outputPath ) && is_readable( $this->outputPath ) ) {
		$_pbet_post_cmd  = [ $_pbet_postbin, $this->outputPath ];
		$_pbet_post_proc = @proc_open( $_pbet_post_cmd, $_pbet_descriptors, $_pbet_post_pipes );

		if ( is_resource( $_pbet_post_proc ) ) {
			fclose( $_pbet_post_pipes[0] );
			fclose( $_pbet_post_pipes[1] );
			$_pbet_post_stderr = (string) stream_get_contents( $_pbet_post_pipes[2] );
			fclose( $_pbet_post_pipes[2] );
			$_pbet_post_exit   = proc_close( $_pbet_post_proc );

			if ( $_pbet_post_exit === 0 ) {
				error_log( '[pb-export-tools] PDF/UA-2 post-processing complete: ' . $this->outputPath );
			} else {
				error_log( '[pb-export-tools] pb-postprocess-pdf failed'
					. ' (exit ' . $_pbet_post_exit . '): ' . $_pbet_post_stderr );
			}
		} else {
			error_log( '[pb-export-tools] Could not start pb-postprocess-pdf; skipping.' );
		}
	}

	// ----- Step 5: clean up temp files -----------------------------------
	if ( isset( $_pbet_processed ) && $_pbet_html_for_prince !== $_pbet_processed ) {
		@unlink( $_pbet_processed );
	}
	@unlink( $_pbet_src_html );
}
// =========================================================================
```

### A4. Verify the file has no PHP syntax errors

```bash
php -l /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php
```

Expected output: `No syntax errors detected in ...`

If you see a parse error, restore the backup (`cp class-pdf.php.bak class-pdf.php`) and check that you pasted the block cleanly without leaving the original line in place.

### A5. Test an export

1. Log into Pressbooks and open any book.
2. Go to **Export** and click **Export your book** with **Print PDF (Prince)** selected.
3. While it runs, tail the debug log in another terminal:
   ```bash
   tail -f /var/www/html/wp-content/debug.log | grep pb-export-tools
   ```
4. You should see:
   ```
   [pb-export-tools] HTML pre-processing succeeded.
   [pb-export-tools] PDF/UA-2 post-processing complete: /var/www/html/wp-content/uploads/...pdf
   ```
5. Download the generated PDF and open it.  In Acrobat go to
   **File → Properties → Description** — the book title should appear in the
   title bar (DisplayDocTitle fix).

### A6. Enabling spoken alt text later

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

### A7. Rolling back

To remove the hack entirely and restore original behaviour:

```bash
cp /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php.bak \
   /var/www/html/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php
```

---

## Option B — mu-plugin approach (survives Pressbooks updates)

Use this when Option A is confirmed working and you want the logic to live
outside Pressbooks core so it survives future `composer update` runs.

### B1. Install the mu-plugin

```bash
cp /opt/pressbooks-export-tools/mu-plugins/pb-export-postprocess.php \
   /var/www/html/wp-content/mu-plugins/
```

Must-use plugins load automatically — no activation step is needed.

### B2. Apply the minimal class-pdf.php patch

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

### B3. Configure binary paths

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

