<?php
/**
 * Pre-patched copy of Pressbooks' inc/modules/export/prince/class-pdf.php.
 *
 * Source: https://github.com/pressbooks/pressbooks (dev branch, GPLv3)
 * Modifications: pressbooks-export-tools accessibility pre/post-processing block
 *   inserted in place of the original convert_file_to_file() call.
 *
 * Usage
 * -----
 * 1. Adjust the two binary paths near the top of the patched block (search for
 *    "← full path to") to match your install.
 * 2. Copy this file to:
 *      <wordpress-root>/wp-content/plugins/pressbooks/inc/modules/export/prince/class-pdf.php
 *    (Back up the original first.)
 * 3. Run `php -l class-pdf.php` to confirm no syntax errors.
 * 4. IMPORTANT: clear PHP OPcache after deploying, otherwise the WP-Cron
 *    background job will keep running the stale compiled bytecode.  The
 *    symptom is [pb-debug] __construct() appearing in the log while
 *    [pb-debug] convert() CALLED never appears — both run in different
 *    PHP processes and OPcache can serve different versions to each.
 *
 *    Clear OPcache:  wp eval 'opcache_reset();'
 *    Or restart:     sudo systemctl restart php8.3-fpm   (adjust version)
 *
 * To roll back, restore your backup or re-install the pressbooks plugin.
 *
 * @author  Pressbooks <code@pressbooks.com>
 * @license GPLv3 (or any later version)
 */

namespace Pressbooks\Modules\Export\Prince;

use function Pressbooks\Sanitize\normalize_css_urls;
use function Pressbooks\Utility\get_contents;
use function Pressbooks\Utility\put_contents;
use Generator;
use Pressbooks\Container;
use Pressbooks\Modules\Export\Export;
use PrinceXMLPhp\PrinceWrapper;

class Pdf extends Export {

	/**
	 * Service URL
	 *
	 * @var string
	 */
	public string $url;

	/**
	 * Fullpath to log file used by Prince.
	 *
	 * @var string
	 */
	public string $logfile;

	/**
	 * Fullpath to book CSS file.
	 *
	 * @var string
	 */
	protected string|false $exportStylePath;

	/**
	 * Fullpath to book JavaScript file.
	 *
	 * @var string
	 */
	protected string|false $exportScriptPath;

	/**
	 * CSS overrides
	 *
	 * @var string
	 */
	protected string $cssOverrides;

	/**
	 * @var string
	 */
	protected string $pdfProfile;

	/**
	 * @var string
	 */
	protected string $pdfOutputIntent;

	/**
	 * @param array $args
	 */
	public function __construct( array $args ) {
		error_log( '[pb-debug] Pdf::__construct() called — class=' . get_class( $this ) );

		if ( ! defined( 'PB_PRINCE_COMMAND' ) ) {
			define( 'PB_PRINCE_COMMAND', '/usr/bin/prince' );
		}

		$this->exportStylePath = $this->getExportStylePath( 'prince' );
		$this->exportScriptPath = $this->getExportScriptPath( 'prince' );
		$this->pdfProfile = $this->getPdfProfile();
		$this->pdfOutputIntent = $this->getPdfOutputIntent();

		// Set the access protected "format/xhtml" URL with a valid timestamp and NONCE
		$timestamp = time();
		$md5 = $this->nonce( $timestamp );
		$this->url = home_url() . "/format/xhtml?timestamp={$timestamp}&hashkey={$md5}";

		error_log( '[pb-debug] Pdf::__construct() exportStylePath=' . var_export( $this->exportStylePath, true )
			. ' exportScriptPath=' . var_export( $this->exportScriptPath, true )
			. ' pdfProfile=' . var_export( $this->pdfProfile, true )
			. ' pdfOutputIntent=' . var_export( $this->pdfOutputIntent, true )
			. ' url=' . $this->url );

		$this->themeOptionsOverrides();
		error_log( '[pb-debug] Pdf::__construct() done' );
	}

	/**
	 * Add $this->url as additional log info, fallback to parent.
	 *
	 * @param $message
	 * @param array $more_info (unused, overridden)
	 */
	public function logError( $message, array $more_info = [] ): void {
		error_log( '[pb-debug] Pdf::logError() called — class=' . get_class( $this ) . ' message=' . $message );

		$more_info['url'] = $this->url;

		parent::logError( $message, $more_info );
	}

	/**
	 * @return string
	 */
	protected function generateFileName() {
		error_log( '[pb-debug] Pdf::generateFileName() called — class=' . get_class( $this ) );
		return $this->timestampedFileName( '.pdf' );
	}

	/**
	 * Verify if body is actual PDF
	 *
	 * @param string $file
	 *
	 * @return bool
	 */
	protected function isPdf( $file ): bool {
		error_log( '[pb-debug] Pdf::isPdf() called — class=' . get_class( $this ) . ' file=' . $file );

		$mime = static::mimeType( $file );

		return ( str_contains( $mime, 'application/pdf' ) );
	}

	/**
	 * @return string
	 */
	protected function getPdfProfile(): string {
		$result = defined( 'PB_PDF_PROFILE' ) ? PB_PDF_PROFILE : '';
		error_log( '[pb-debug] Pdf::getPdfProfile() called — class=' . get_class( $this ) . ' result=' . var_export( $result, true ) );
		return $result;
	}

	/**
	 * @return string
	 */
	protected function getPdfOutputIntent(): string {
		$result = defined( 'PB_PDF_OUTPUT_INTENT' ) ? PB_PDF_OUTPUT_INTENT : '';
		error_log( '[pb-debug] Pdf::getPdfOutputIntent() called — class=' . get_class( $this ) . ' result=' . var_export( $result, true ) );
		return $result;
	}

	/**
	 * Return kneaded CSS string
	 *
	 * @return string
	 * @throws ContainerExceptionInterface
	 * @throws NotFoundExceptionInterface
	 */
	protected function kneadCss(): string {
		error_log( '[pb-debug] Pdf::kneadCss() called — class=' . get_class( $this ) );

		$styles = Container::get( 'Styles' );

		$scss = get_contents( $this->exportStylePath );

		$custom_styles = $styles->getPrincePost();
		if ( $custom_styles && ! empty( $custom_styles->post_content ) ) {
			// append the user's custom styles to the theme stylesheet prior to compilation
			$scss .= "\n" . $custom_styles->post_content;
		}

		$css = $styles->customize( 'prince', $scss, $this->cssOverrides );

		$css = normalize_css_urls( $css, $this->urlPath() );

		if ( WP_DEBUG ) {
			Container::get( 'Sass' )->debug( $css, $scss, 'prince' );
		}

		return $css;
	}

	/**
	 * Convert the directory containing `$this->exportStylePath` to a URL that can be used by services like DocRaptor
	 * Useful for sending assets like images/asterisk.png, images/em-dash.png, ...
	 *
	 * @return string
	 * @throws ContainerExceptionInterface
	 * @throws NotFoundExceptionInterface
	 */
	protected function urlPath() {
		error_log( '[pb-debug] Pdf::urlPath() called — class=' . get_class( $this ) );
		$dir = str_replace( Container::get( 'Styles' )->getDir(), '', pathinfo( $this->exportStylePath, PATHINFO_DIRNAME ) );
		$dir = ltrim( $dir, '/' );
		$url_path = trailingslashit( get_stylesheet_directory_uri() ) . $dir;
		return set_url_scheme( $url_path );
	}

	/**
	 * Override based on Theme Options
	 */
	protected function themeOptionsOverrides(): void {
		error_log( '[pb-debug] Pdf::themeOptionsOverrides() called — class=' . get_class( $this ) );

		// --------------------------------------------------------------------
		// CSS

		$scss = '';
		$scss = apply_filters( 'pb_pdf_css_override', $scss ) . "\n";

		// Copyright
		// Please be kind, help Pressbooks grow by leaving this on!
		if ( empty( $GLOBALS['PB_SECRET_SAUCE']['TURN_OFF_FREEBIE_NOTICES_PDF'] ) ) {
			$freebie_notice = __( 'This book was produced with Pressbooks (https://pressbooks.com) and rendered with Prince.', 'pressbooks' );
			$scss .= '#copyright-page .ugc > p:last-of-type::after { display:block; margin-top: 1em; content: "' . $freebie_notice . '" }' . "\n";
		}

		$this->cssOverrides = $scss;

		// --------------------------------------------------------------------
		// Hacks

		$hacks = [];
		$hacks = apply_filters( 'pb_pdf_hacks', $hacks );

		// Append endnotes to URL?
		if ( isset( $hacks['pdf_footnotes_style'] ) && 'endnotes' === $hacks['pdf_footnotes_style'] ) {
			$this->url .= '&endnotes=true';
			$_GET['endnotes'] = 'true';
		}

	}

	/**
	 * For expensive functions we use a generator to allow the caller to yield control back to the event loop.
	 *
	 * @return Generator
	 * @throws ContainerExceptionInterface
	 * @throws NotFoundExceptionInterface
	 * @throws \Exception
	 */
	public function convert(): Generator {
		error_log( '[pb-debug] Pdf::convert() called — class=' . get_class( $this ) );

		if ( empty( $this->exportStylePath ) || ! is_file( $this->exportStylePath ) ) {
			error_log( '[pb-debug] Pdf::convert() ERROR: exportStylePath not set or not a file — aborting.' );
			$this->logError( '$this->exportStylePath must be set before calling convert().' );
			yield 'error' => '$this->exportStylePath must be set before calling convert().';
			return false;
		}

		yield 35 => __( 'Setting up conversion...', 'pressbooks' );

		// Set logfile
		$this->logfile = $this->createTmpFile();

		// Set filename
		$filename = $this->generateFileName();
		$this->outputPath = $filename;

		yield 40 => __( 'Loading fonts...', 'pressbooks' );
		// Fonts
		Container::get( 'GlobalTypography' )->getFonts();

		yield 50 => __( 'Generating CSS...', 'pressbooks' );
		// CSS
		$this->truncateExportStylesheets( 'prince' );
		$timestamp = time();
		$css = $this->kneadCss();
		$css_file = Container::get( 'Sass' )->pathToUserGeneratedCss() . "/prince-$timestamp.css";
		$scoped_file = Container::get( 'Sass' )->pathToUserGeneratedCss() . '/scopedstyles.css';
		put_contents( $css_file, $css );

		yield 55 => __( 'Loading Converter...', 'pressbooks' );
		// Initialize Prince
		$prince = new PrinceWrapper( PB_PRINCE_COMMAND );
		$prince->setHTML( true );
		$prince->setCompress( true );
		$prince->setHttpTimeout( defined( 'WP_TESTS_MULTISITE' ) ? 5 : 600 ); // 5 seconds for tests, 10 minutes for production
		$prince->setInputType( 'xml' );
		if ( defined( 'WP_ENV' ) && ( WP_ENV === 'development' ) ) {
			$prince->setInsecure( true );
		}

		yield 56 => __( 'Setting up PDF options...', 'pressbooks' );
		// PDF Profile configuration
		if ( $this->pdfProfile && $this->pdfOutputIntent ) {
			$prince->setPDFProfile( $this->pdfProfile );
			$prince->setPDFOutputIntent( $this->pdfOutputIntent );
		} elseif ( stripos( get_class( $this ), 'print' ) === false && empty( $this->pdfProfile ) ) {
			$prince->setPDFProfile( 'PDF/UA-1' );
		}

		yield 60 => __( 'Adding stylesheets and scripts...', 'pressbooks' );
		// Add resources
		$prince->addStyleSheet( $css_file );
		$prince->addStyleSheet( $scoped_file );
		/** @var Assets $assets */
		$assets = app( 'Assets' );
		$js_path = $assets->getAssetUrl( 'assets/src/scripts/export-footnotes.js' );
		$prince->addScript( $js_path );

		if ( $this->exportScriptPath ) {
			$prince->addScript( $this->exportScriptPath );
		}
		$prince->setLog( $this->logfile );

		yield 65 => __( 'Creating file...', 'pressbooks' );
		// Convert
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

		if ( is_countable( $msg ) && count( $msg ) ) {
			$this->logError( get_contents( $this->logfile ), [ 'warning' => 1 ] );
			yield 80 => __( 'Conversion completed with warnings.', 'pressbooks' );
		} else {
			yield 80 => __( 'Conversion completed successfully.', 'pressbooks' );
		}

		return $retval;
	}

	public function validate(): Generator {
		error_log( '[pb-debug] Pdf::validate() called — class=' . get_class( $this ) . ' outputPath=' . ( $this->outputPath ?? 'NOT SET' ) );
		yield 90 => __( 'Validating PDF.', 'pressbooks' );
		if ( ! $this->isPdf( $this->outputPath ) ) {
			$this->logError( get_contents( $this->logfile ) );
			yield 'error' => __( 'PDF validation failed.', 'pressbooks' );
			return false;
		}

		yield 100 => __( 'PDF Validation successful.', 'pressbooks' );
		return true;
	}
}
