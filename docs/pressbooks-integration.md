# Pressbooks integration guide

This document describes how to wire `pressbooks-export-tools` into an existing
Pressbooks + Prince XML instance so that non-technical authors can click the
normal **Export → Print PDF (Prince)** button and automatically receive:

- math images tagged with `role="math"` (Prince `Formula` structure elements)
- spoken alt text replacing raw LaTeX on math images (optional; requires SRE)
- PDF/UA-2 metadata fixes (`DisplayDocTitle`, `pdfuaid:part=2` XMP)

> **MacGyver note** — this setup is intentionally provisional and targets a
> specific internal instance used for PDF generation and author training.  The
> approach is designed to be low-risk: every step has a fallback so that exports
> continue to work even when the Python tooling is unavailable.

---

## 1. Server prerequisites

All commands that follow must be run as (or accessible to) the web-server user
(`www-data` on most Debian/Ubuntu installs).

### 1a. Python package

```bash
# Install into the system Python or a dedicated venv.
# Using a venv is recommended; activate it before the next steps.
pip install -e /path/to/pressbooks-export-tools[pdf]
```

Verify the CLI tools are on PATH and callable by `www-data`:

```bash
sudo -u www-data which pb-export
sudo -u www-data pb-export --help
sudo -u www-data which pb-postprocess-pdf
sudo -u www-data pb-postprocess-pdf --help
```

If the binaries are installed in a venv, add the venv's `bin/` directory to
`www-data`'s `PATH` (e.g. via `/etc/environment` or the PHP `open_basedir`
configuration).

### 1b. Node.js and Speech Rule Engine (optional — spoken alt text only)

The `--spoken-alt-text` flag and the SRE backend require Node.js ≥ 18.

```bash
# Install Node.js via nvm or your distribution's package manager.
node --version   # should print v18+

# Install the Node dependencies inside the repo.
npm install --prefix /path/to/pressbooks-export-tools/src/pressbooks_export/math/backends/node

# Verify SRE is reachable by www-data.
sudo -u www-data node /path/to/.../node/sre.js x
```

---

## 2. Install the mu-plugin

```bash
cp /path/to/pressbooks-export-tools/mu-plugins/pb-export-postprocess.php \
   /var/www/html/wp-content/mu-plugins/
```

Must-use plugins are loaded automatically — no activation step is needed.

Visit **Dashboard → Settings → PB Export Tools** to confirm the plugin loaded
and to configure the binary paths.  The status notices on the settings page
indicate whether `pb-export` and `pb-postprocess-pdf` were found.

---

## 3. Patch `class-pdf.php`

The mu-plugin registers WordPress hooks but cannot fire them itself — something
inside Pressbooks's Prince export class must call `apply_filters` /
`do_action` at the right moments.  The minimal patch below does exactly that.

**File**: `wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php`

Locate the existing call to `$prince->convert_file_to_file(…)` (around line
145 in Pressbooks 6.x) and replace the surrounding block with:

```php
// --- pressbooks-export-tools hook: HTML pre-processing -------------------
// Write the raw HTML to a secure temp file (not web-accessible).
$_pb_et_tmp_html = tempnam( sys_get_temp_dir(), 'pb_prince_src_' ) . '.html';
file_put_contents( $_pb_et_tmp_html, file_get_contents( $this->url ) );

// Give the mu-plugin a chance to run pb-export on the HTML.
// Falls back to $_pb_et_tmp_html unchanged when the plugin is absent or fails.
$_pb_et_html_for_prince = apply_filters(
    'pb_export_tools_preprocess_html_path',
    $_pb_et_tmp_html,
);

// --- Prince conversion (uses processed HTML instead of the live URL) -----
$retval = $prince->convert_file_to_file( $_pb_et_html_for_prince, $this->outputPath, $msg );

// --- pressbooks-export-tools hook: PDF post-processing -------------------
do_action( 'pb_export_tools_postprocess_pdf', $this->outputPath );

// --- Cleanup temp files ---------------------------------------------------
do_action( 'pb_export_tools_cleanup_temp_html', $_pb_et_html_for_prince, $_pb_et_tmp_html );
@unlink( $_pb_et_tmp_html );
// -------------------------------------------------------------------------
```

> The original line was:
> ```php
> $retval = $prince->convert_file_to_file( $this->url, $this->outputPath, $msg );
> ```

If `pb_export_tools_preprocess_html_path` has no listeners (i.e. the mu-plugin
is not loaded), `apply_filters` returns the value unchanged and the export
behaves exactly as before.

---

## 4. Configure the admin settings

Visit **Dashboard → Settings → PB Export Tools** and verify:

| Setting | Recommended value |
|---|---|
| Enable post-processing | ✓ checked |
| Spoken alt text | leave unchecked until SRE is confirmed working |
| pb-export path | full path, e.g. `/usr/local/bin/pb-export` |
| pb-postprocess-pdf path | full path, e.g. `/usr/local/bin/pb-postprocess-pdf` |

Using full paths avoids PATH lookup issues when PHP runs under a restricted
environment (FastCGI, FPM, etc.).

---

## 5. Test the pipeline

1. Open any book on the instance and export a **Print PDF (Prince)**.
2. Check the WordPress debug log (`wp-content/debug.log` or PHP error log) for
   `[pb-export-tools]` lines confirming success:
   ```
   [pb-export-tools] HTML pre-processing succeeded.
   [pb-export-tools] PDF/UA-2 post-processing complete: /path/to/book.pdf
   ```
3. Open the PDF in Acrobat or a PDF inspector and confirm:
   - **Document Properties → Description** shows the book title in the viewer
     title bar (`DisplayDocTitle`)
   - **Document Properties → Advanced** or an XMP viewer shows
     `pdfuaid:part = 2`
4. Run veraPDF on the output to check PDF/UA-2 compliance:
   ```bash
   verapdf --flavour ua2 /path/to/book.pdf
   ```

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Warning banner on settings page | Binary not found by web-server user | Use a full path; check `sudo -u www-data which pb-export` |
| No `[pb-export-tools]` lines in log | WP_DEBUG_LOG not enabled, or patch not applied | Enable `define('WP_DEBUG_LOG', true)` in `wp-config.php` |
| Export still works but no fixes | `pb-export` exits non-zero | Check stderr in the log; run `pb-export --help` as `www-data` |
| Export broken after patch | Syntax error in patch | Restore original line; verify patch against the version of Pressbooks installed |

---

## 7. Future direction

Once the MacGyver phase proves out the pipeline:

- Submit the `apply_filters` / `do_action` call points as a pull request to
  Pressbooks upstream, so the core patch is no longer needed.
- Package the mu-plugin for distribution via the WordPress plugin directory or
  as a Composer dependency.
- Add a Pressbooks-native export format option so authors can select
  "Accessible PDF (Prince + export-tools)" from the export screen.
