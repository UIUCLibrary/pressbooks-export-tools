<?php
/**
 * Drop-in replacement for Pressbooks' inc/modules/export/prince/class-pdf.php.
 *
 * Source: https://github.com/UIUCLibrary/pressbooks (GPLv3)
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
 * 4. Clear PHP OPcache after deploying:
 *      wp eval 'opcache_reset();'
 *    Or restart:  sudo systemctl restart php8.3-fpm   (adjust version)
 *
 * To roll back, restore your backup or re-install the pressbooks plugin.
 *
 * @author  Pressbooks <code@pressbooks.com>
 * @license GPLv3 (or any later version)
 */

namespace Pressbooks\Modules\Export\Prince;

use function Pressbooks\Sanitize\normalize_css_urls;
use PressbooksMix\Assets;
use Pressbooks\Container;
use Pressbooks\Modules\Export\Export;

class Pdf extends Export {

	/**
	 * Service URL
	 *
	 * @var string
	 */
	public $url;

	/**
	 * Fullpath to log file used by Prince.
	 *
	 * @var string
	 */
	public $logfile;

	/**
	 * Fullpath to book CSS file.
	 *
	 * @var string
	 */
	protected $exportStylePath;

	/**
	 * Fullpath to book JavaScript file.
	 *
	 * @var string
	 */
	protected $exportScriptPath;

	/**
	 * CSS overrides
	 *
	 * @var string
	 */
	protected $cssOverrides;

	/**
	 * @var string
	 */
	protected $pdfProfile;

	/**
	 * @var string
	 */
	protected $pdfOutputIntent;

	/**
	 * @param array $args
	 */
	function __construct( array $args ) {

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

		$this->themeOptionsOverrides();
	}

	/**
	 * Create $this->outputPath
	 *
	 * @return bool
	 */
	function convert() {

		// Sanity check
		if ( empty( $this->exportStylePath ) || ! is_file( $this->exportStylePath ) ) {
			$this->logError( '$this->exportStylePath must be set before calling convert().' );
			return false;
		}

		// Set logfile
		$this->logfile = $this->createTmpFile();

		// Set filename
		$filename = $this->generateFileName();
		$this->outputPath = $filename;

		// Fonts
		Container::get( 'GlobalTypography' )->getFonts();

		// CSS
		$this->truncateExportStylesheets( 'prince' );
		$timestamp = time();
		$css = $this->kneadCss();
		$css_file = Container::get( 'Sass' )->pathToUserGeneratedCss() . "/prince-$timestamp.css";
		\Pressbooks\Utility\put_contents( $css_file, $css );

		// --------------------------------------------------------------------
		// Save PDF as file in exports folder

		$prince = new \PrinceXMLPhp\PrinceWrapper( PB_PRINCE_COMMAND );
		$prince->setHTML( true );
		$prince->setCompress( true );
		$prince->setHttpTimeout( max( ini_get( 'max_execution_time' ), 30 ) );
		$prince->setInputType( 'xml' );
		if ( defined( 'WP_ENV' ) && ( WP_ENV === 'development' ) ) {
			$prince->setInsecure( true );
		}

		if ( $this->pdfProfile && $this->pdfOutputIntent ) {
			$prince->setPDFProfile( $this->pdfProfile );
			$prince->setPDFOutputIntent( $this->pdfOutputIntent );
		} elseif ( stripos( get_class( $this ), 'print' ) === false && empty( $this->pdfProfile ) ) {
			// PDF for digital distribution without any PB_PDF_PROFILE
			// Use PDF/UA-1, enhanced for accessibility.
			$prince->setPDFProfile( 'PDF/UA-1' );
		}

		$prince->addStyleSheet( $css_file );
		$assets = new Assets( 'pressbooks', 'plugin' );
		$js_path = $assets->getPath( 'scripts/export-footnotes.js' );
		$prince->addScript( $js_path );

		if ( $this->exportScriptPath ) {
			$prince->addScript( $this->exportScriptPath );
		}
		$prince->setLog( $this->logfile );

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

			// Count math elements in clean.html to confirm MathML conversion worked.
			if ( $_pbet_clean_exists && $_pbet_clean_size > 0 ) {
				$_pbet_clean_content = file_get_contents( $_pbet_clean_html );
				$_pbet_math_count    = preg_match_all( '/<math[\s>]/', $_pbet_clean_content );
				$_pbet_img_count     = preg_match_all( '/class="[^"]*\blatex\b/', $_pbet_clean_content );
				unset( $_pbet_clean_content );
				error_log( '[pb-export-tools] Step 2: clean.html math elements=<math>:' . $_pbet_math_count
					. ' remaining <img class=latex>:' . $_pbet_img_count );
			}

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

		// Prince XML is very flexible. There could be errors but Prince will still render a PDF.
		// We want to log those errors but we won't alert the user.
		if ( is_countable( $msg ) && count( $msg ) ) {
			$this->logError( \Pressbooks\Utility\get_contents( $this->logfile ), [ 'warning' => 1 ] );
		}

		return $retval;
	}

	/**
	 * Check the sanity of $this->outputPath
	 *
	 * @return bool
	 */
	function validate() {
		// Is this a PDF?
		if ( ! $this->isPdf( $this->outputPath ) ) {
			$this->logError( \Pressbooks\Utility\get_contents( $this->logfile ) );
			return false;
		}
		return true;
	}

	/**
	 * Add $this->url as additional log info, fallback to parent.
	 *
	 * @param $message
	 * @param array $more_info (unused, overridden)
	 */
	function logError( $message, array $more_info = [] ) {

		$more_info['url'] = $this->url;

		parent::logError( $message, $more_info );
	}

	/**
	 * @return string
	 */
	protected function generateFileName() {
		return $this->timestampedFileName( '.pdf' );
	}

	/**
	 * Verify if body is actual PDF
	 *
	 * @param string $file
	 *
	 * @return bool
	 */
	protected function isPdf( $file ) {

		$mime = static::mimeType( $file );

		return ( strpos( $mime, 'application/pdf' ) !== false );
	}

	/**
	 * @return string
	 */
	protected function getPdfProfile() {
		if ( defined( 'PB_PDF_PROFILE' ) ) {
			return PB_PDF_PROFILE;
		}
		return '';
	}

	/**
	 * @return string
	 */
	protected function getPdfOutputIntent() {
		if ( defined( 'PB_PDF_OUTPUT_INTENT' ) ) {
			return PB_PDF_OUTPUT_INTENT;
		}
		return '';
	}

	/**
	 * Return kneaded CSS string
	 *
	 * @return string
	 */
	protected function kneadCss() {

		$styles = Container::get( 'Styles' );

		$scss = \Pressbooks\Utility\get_contents( $this->exportStylePath );

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
	 */
	protected function urlPath() {
		$dir = str_replace( Container::get( 'Styles' )->getDir(), '', pathinfo( $this->exportStylePath, PATHINFO_DIRNAME ) );
		$dir = ltrim( $dir, '/' );
		$url_path = trailingslashit( get_stylesheet_directory_uri() ) . $dir;
		$url_path = set_url_scheme( $url_path );

		return $url_path;
	}

	/**
	 * Override based on Theme Options
	 */
	protected function themeOptionsOverrides() {

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
		}

	}

}
