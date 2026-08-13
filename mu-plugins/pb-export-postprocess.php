<?php
/**
 * Plugin Name: Pressbooks Export Tools Integration
 * Plugin URI:  https://github.com/UIUCLibrary/pressbooks-export-tools
 * Description: Pre-processes Pressbooks HTML before Prince XML and applies PDF/UA-2 fixes after export.
 * Version:     0.1.0
 * Author:      UIUCLibrary
 * License:     GPL-2.0-or-later
 *
 * This mu-plugin wires the pressbooks-export-tools Python package into the
 * Pressbooks Prince PDF export pipeline.  It registers two custom WordPress
 * hooks that a minimal patch to inc/modules/export/prince/class-pdf.php must
 * call at the right moments (see docs/pressbooks-integration.md for the patch).
 *
 * Hook contract
 * -------------
 * Filter  pb_export_tools_preprocess_html_path($html_path)
 *   Called with the absolute path of the temporary HTML file written from
 *   $this->url, before that file is handed to Prince.  Returns the path
 *   that Prince should use — either the original path (fallback) or a new
 *   temp file created by pb-export.
 *
 * Action  pb_export_tools_postprocess_pdf($pdf_path)
 *   Called with the absolute path of the PDF that Prince just wrote.
 *   Applies PDF/UA-2 fixes (DisplayDocTitle, pdfuaid:part XMP) in-place.
 *
 * Action  pb_export_tools_cleanup_temp_html($processed_path, $original_path)
 *   Called after Prince finishes and postprocess_pdf has run.  Removes the
 *   processed HTML temp file when it differs from the original.
 *
 * Admin toggle
 * ------------
 * Dashboard → Settings → PB Export Tools
 * The checkbox controls all pipeline activity.  A separate checkbox enables
 * the slower spoken-alt-text flag (requires Node.js + Speech Rule Engine).
 *
 * @package UIUCLibrary\Pressbooks\ExportTools
 */

declare(strict_types=1);

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

// ---------------------------------------------------------------------------
// Option keys
// ---------------------------------------------------------------------------

const PB_EXPORT_TOOLS_OPTION      = 'pb_export_tools_enabled';
const PB_EXPORT_TOOLS_SPOKEN_ALT  = 'pb_export_tools_spoken_alt_text';
const PB_EXPORT_TOOLS_IMAGE_ONLY  = 'pb_export_tools_image_only';
const PB_EXPORT_TOOLS_BIN         = 'pb_export_tools_bin_path';
const PB_EXPORT_TOOLS_POSTBIN     = 'pb_export_tools_postprocess_bin_path';

// ---------------------------------------------------------------------------
// Module-level state: processed HTML path shared between the preprocess
// filter and the postprocess action within the same request.
// ---------------------------------------------------------------------------

/** @var string|null Absolute path of the processed HTML written by pb-export. */
$_pb_export_tools_processed_html_path = null;

// ---------------------------------------------------------------------------
// Admin settings
// ---------------------------------------------------------------------------

add_action( 'admin_menu', 'pb_export_tools_add_settings_page' );
add_action( 'admin_init', 'pb_export_tools_register_settings' );

/**
 * Register the Settings → PB Export Tools page under the Dashboard.
 */
function pb_export_tools_add_settings_page(): void {
	add_options_page(
		__( 'Pressbooks Export Tools', 'pb-export-tools' ),
		__( 'PB Export Tools', 'pb-export-tools' ),
		'manage_options',
		'pb-export-tools',
		'pb_export_tools_settings_page',
	);
}

/**
 * Register settings with the WordPress Settings API.
 */
function pb_export_tools_register_settings(): void {
	register_setting(
		'pb_export_tools',
		PB_EXPORT_TOOLS_OPTION,
		[
			'type'              => 'boolean',
			'default'           => true,
			'sanitize_callback' => 'rest_sanitize_boolean',
		]
	);
	register_setting(
		'pb_export_tools',
		PB_EXPORT_TOOLS_SPOKEN_ALT,
		[
			'type'              => 'boolean',
			'default'           => false,
			'sanitize_callback' => 'rest_sanitize_boolean',
		]
	);
	register_setting(
		'pb_export_tools',
		PB_EXPORT_TOOLS_IMAGE_ONLY,
		[
			'type'              => 'boolean',
			'default'           => false,
			'sanitize_callback' => 'rest_sanitize_boolean',
		]
	);
	register_setting(
		'pb_export_tools',
		PB_EXPORT_TOOLS_BIN,
		[
			'type'              => 'string',
			'default'           => 'pb-export',
			'sanitize_callback' => 'sanitize_text_field',
		]
	);
	register_setting(
		'pb_export_tools',
		PB_EXPORT_TOOLS_POSTBIN,
		[
			'type'              => 'string',
			'default'           => 'pb-postprocess-pdf',
			'sanitize_callback' => 'sanitize_text_field',
		]
	);
}

/**
 * Render the Settings → PB Export Tools page.
 */
function pb_export_tools_settings_page(): void {
	if ( ! current_user_can( 'manage_options' ) ) {
		return;
	}

	$bin          = (string) get_option( PB_EXPORT_TOOLS_BIN, 'pb-export' );
	$postbin      = (string) get_option( PB_EXPORT_TOOLS_POSTBIN, 'pb-postprocess-pdf' );
	$bin_found    = pb_export_tools_resolve_bin( $bin ) !== null;
	$postbin_found = pb_export_tools_resolve_bin( $postbin ) !== null;
	?>
	<div class="wrap">
		<h1><?php echo esc_html( get_admin_page_title() ); ?></h1>

		<?php if ( ! $bin_found ) : ?>
		<div class="notice notice-warning">
			<p>
			<?php
			printf(
				/* translators: %s: configured binary name/path */
				esc_html__( 'pb-export binary not found at "%s". HTML pre-processing will be skipped until the path is corrected.', 'pb-export-tools' ),
				esc_html( $bin )
			);
			?>
			</p>
		</div>
		<?php endif; ?>

		<?php if ( ! $postbin_found ) : ?>
		<div class="notice notice-warning">
			<p>
			<?php
			printf(
				/* translators: %s: configured binary name/path */
				esc_html__( 'pb-postprocess-pdf binary not found at "%s". PDF/UA-2 post-processing will be skipped until the path is corrected.', 'pb-export-tools' ),
				esc_html( $postbin )
			);
			?>
			</p>
		</div>
		<?php endif; ?>

		<form action="options.php" method="post">
			<?php settings_fields( 'pb_export_tools' ); ?>
			<table class="form-table" role="presentation">
				<tr>
					<th scope="row">
						<?php esc_html_e( 'Enable post-processing', 'pb-export-tools' ); ?>
					</th>
					<td>
						<label>
							<input
								type="checkbox"
								name="<?php echo esc_attr( PB_EXPORT_TOOLS_OPTION ); ?>"
								value="1"
								<?php checked( (bool) get_option( PB_EXPORT_TOOLS_OPTION, true ) ); ?>
							/>
							<?php esc_html_e( 'Apply accessibility post-processing to Prince PDF exports', 'pb-export-tools' ); ?>
						</label>
					</td>
				</tr>
				<tr>
					<th scope="row">
						<?php esc_html_e( 'Spoken alt text', 'pb-export-tools' ); ?>
					</th>
					<td>
						<label>
							<input
								type="checkbox"
								name="<?php echo esc_attr( PB_EXPORT_TOOLS_SPOKEN_ALT ); ?>"
								value="1"
								<?php checked( (bool) get_option( PB_EXPORT_TOOLS_SPOKEN_ALT, false ) ); ?>
							/>
							<?php esc_html_e( 'Replace raw LaTeX alt text with plain-English spoken descriptions (requires Node.js + Speech Rule Engine; adds processing time)', 'pb-export-tools' ); ?>
						</label>
					</td>
				</tr>
				<tr>
					<th scope="row">
						<?php esc_html_e( 'Gentle pipeline (image-only)', 'pb-export-tools' ); ?>
					</th>
					<td>
						<label>
							<input
								type="checkbox"
								name="<?php echo esc_attr( PB_EXPORT_TOOLS_IMAGE_ONLY ); ?>"
								value="1"
								<?php checked( (bool) get_option( PB_EXPORT_TOOLS_IMAGE_ONLY, false ) ); ?>
							/>
							<?php esc_html_e( 'Keep Pressbooks math images intact (do not convert to MathML). Visual rendering stays pixel-perfect. MathML is generated separately and attached as Associated Files on Figure structure elements during PDF post-processing.', 'pb-export-tools' ); ?>
						</label>
					</td>
				</tr>
				<tr>
					<th scope="row">
						<label for="<?php echo esc_attr( PB_EXPORT_TOOLS_BIN ); ?>">
							<?php esc_html_e( 'pb-export path', 'pb-export-tools' ); ?>
						</label>
					</th>
					<td>
						<input
							type="text"
							id="<?php echo esc_attr( PB_EXPORT_TOOLS_BIN ); ?>"
							name="<?php echo esc_attr( PB_EXPORT_TOOLS_BIN ); ?>"
							value="<?php echo esc_attr( $bin ); ?>"
							class="regular-text"
						/>
						<p class="description">
							<?php esc_html_e( 'Command name or full path (e.g. /usr/local/bin/pb-export). Must be reachable by the web-server user (www-data).', 'pb-export-tools' ); ?>
						</p>
					</td>
				</tr>
				<tr>
					<th scope="row">
						<label for="<?php echo esc_attr( PB_EXPORT_TOOLS_POSTBIN ); ?>">
							<?php esc_html_e( 'pb-postprocess-pdf path', 'pb-export-tools' ); ?>
						</label>
					</th>
					<td>
						<input
							type="text"
							id="<?php echo esc_attr( PB_EXPORT_TOOLS_POSTBIN ); ?>"
							name="<?php echo esc_attr( PB_EXPORT_TOOLS_POSTBIN ); ?>"
							value="<?php echo esc_attr( $postbin ); ?>"
							class="regular-text"
						/>
						<p class="description">
							<?php esc_html_e( 'Command name or full path for the PDF/UA-2 post-processor (e.g. /usr/local/bin/pb-postprocess-pdf).', 'pb-export-tools' ); ?>
						</p>
					</td>
				</tr>
			</table>
			<?php submit_button(); ?>
		</form>
	</div>
	<?php
}

// ---------------------------------------------------------------------------
// Pipeline hooks
// ---------------------------------------------------------------------------

/**
 * Filter: pb_export_tools_preprocess_html_path
 *
 * Runs pb-export --format html --prince-preprocess on the temp HTML file that
 * class-pdf.php writes before handing it to Prince.  On success, returns the
 * path to a new processed temp file; on any failure, returns the original path
 * unchanged so the export can continue without interruption.
 */
add_filter( 'pb_export_tools_preprocess_html_path', 'pb_export_tools_preprocess_html' );

function pb_export_tools_preprocess_html( string $html_path ): string {
	global $_pb_export_tools_processed_html_path;

	if ( ! get_option( PB_EXPORT_TOOLS_OPTION, true ) ) {
		return $html_path;
	}

	$bin = pb_export_tools_resolve_bin( (string) get_option( PB_EXPORT_TOOLS_BIN, 'pb-export' ) );
	if ( $bin === null ) {
		error_log( '[pb-export-tools] pb-export not found; skipping HTML pre-processing.' );
		return $html_path;
	}

	$processed_path = tempnam( sys_get_temp_dir(), 'pb_export_processed_' );
	if ( $processed_path === false ) {
		error_log( '[pb-export-tools] Could not create temp file; skipping HTML pre-processing.' );
		return $html_path;
	}
	// Give the file an .html extension so pb-export recognises it.
	$processed_html = $processed_path . '.html';
	rename( $processed_path, $processed_html );
	$processed_path = $processed_html;

	$cmd = [ $bin, '--format', 'html', '--prince-preprocess' ];
	if ( get_option( PB_EXPORT_TOOLS_SPOKEN_ALT, false ) ) {
		$cmd[] = '--spoken-alt-text';
	}
	if ( get_option( PB_EXPORT_TOOLS_IMAGE_ONLY, false ) ) {
		$cmd[] = '--image-only';
	}
	$cmd[] = '--output';
	$cmd[] = $processed_path;
	$cmd[] = $html_path;

	[ $exit_code, $stderr ] = pb_export_tools_run( $cmd );

	if ( $exit_code !== 0 || ! file_exists( $processed_path ) || filesize( $processed_path ) === 0 ) {
		error_log( sprintf(
			'[pb-export-tools] pb-export exited %d; stderr: %s — falling back to unprocessed HTML.',
			$exit_code,
			$stderr,
		) );
		@unlink( $processed_path );
		return $html_path;
	}

	// Store so the postprocess action can pass --html to pb-postprocess-pdf.
	$_pb_export_tools_processed_html_path = $processed_path;

	error_log( '[pb-export-tools] HTML pre-processing succeeded.' );
	return $processed_path;
}

/**
 * Action: pb_export_tools_postprocess_pdf
 *
 * Runs pb-postprocess-pdf on the PDF that Prince just created to inject
 * ViewerPreferences/DisplayDocTitle and pdfuaid:part=2 XMP metadata.
 * When a processed HTML file was produced by the preprocess step, also
 * passes --html so MathML can be attached to the math structure elements.
 */
add_action( 'pb_export_tools_postprocess_pdf', 'pb_export_tools_postprocess_pdf' );

function pb_export_tools_postprocess_pdf( string $pdf_path ): void {
	global $_pb_export_tools_processed_html_path;

	if ( ! get_option( PB_EXPORT_TOOLS_OPTION, true ) ) {
		return;
	}
	if ( ! file_exists( $pdf_path ) || ! is_readable( $pdf_path ) ) {
		error_log( "[pb-export-tools] PDF not found or not readable: $pdf_path" );
		return;
	}

	$bin = pb_export_tools_resolve_bin( (string) get_option( PB_EXPORT_TOOLS_POSTBIN, 'pb-postprocess-pdf' ) );
	if ( $bin === null ) {
		error_log( '[pb-export-tools] pb-postprocess-pdf not found; skipping PDF post-processing.' );
		return;
	}

	$cmd = [ $bin, $pdf_path ];

	// If we have a processed HTML file, pass it so MathML can be injected.
	if (
		$_pb_export_tools_processed_html_path !== null
		&& file_exists( $_pb_export_tools_processed_html_path )
	) {
		$cmd[] = '--html';
		$cmd[] = $_pb_export_tools_processed_html_path;
	}

	[ $exit_code, $stderr ] = pb_export_tools_run( $cmd );

	if ( $exit_code !== 0 ) {
		error_log( sprintf(
			'[pb-export-tools] pb-postprocess-pdf exited %d; stderr: %s',
			$exit_code,
			$stderr,
		) );
		return;
	}

	error_log( "[pb-export-tools] PDF/UA-2 post-processing complete: $pdf_path" );
}

/**
 * Action: pb_export_tools_cleanup_temp_html
 *
 * Removes the processed temp HTML file created by the preprocess filter when
 * it differs from the original (i.e. when pre-processing actually ran).
 *
 * @param string $processed_path Path returned by the preprocess filter.
 * @param string $original_path  Path that was passed into the filter.
 */
add_action( 'pb_export_tools_cleanup_temp_html', 'pb_export_tools_cleanup_temp_html', 10, 2 );

function pb_export_tools_cleanup_temp_html( string $processed_path, string $original_path ): void {
	if ( $processed_path !== $original_path && file_exists( $processed_path ) ) {
		@unlink( $processed_path );
	}
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Resolve a binary name or absolute path to an executable path, or null.
 *
 * Accepts either a bare command name (looked up on PATH via `which`) or an
 * absolute/relative path.  Returns null when the binary cannot be found or
 * is not executable.
 *
 * @param  string      $bin Command name or file path.
 * @return string|null Resolved executable path, or null on failure.
 */
function pb_export_tools_resolve_bin( string $bin ): ?string {
	if ( $bin === '' ) {
		return null;
	}
	// Absolute or relative path supplied — check directly.
	if ( str_starts_with( $bin, '/' ) || str_starts_with( $bin, './' ) ) {
		return is_executable( $bin ) ? $bin : null;
	}
	// Bare command name — search PATH.
	$found = trim( (string) shell_exec( 'which ' . escapeshellarg( $bin ) . ' 2>/dev/null' ) );
	return ( $found !== '' && is_executable( $found ) ) ? $found : null;
}

/**
 * Run a command as a subprocess and return [exit_code, stderr_output].
 *
 * Uses proc_open with an array command to avoid shell-injection risks.
 * stdout is discarded; stderr is captured for error logging.
 *
 * @param  string[] $cmd Command and arguments (no shell escaping needed).
 * @return array{int, string} [exit_code, stderr]
 */
function pb_export_tools_run( array $cmd ): array {
	$descriptors = [
		0 => [ 'pipe', 'r' ],  // stdin  (closed immediately)
		1 => [ 'pipe', 'w' ],  // stdout (discarded)
		2 => [ 'pipe', 'w' ],  // stderr (captured)
	];

	$proc = proc_open( $cmd, $descriptors, $pipes );
	if ( ! is_resource( $proc ) ) {
		return [ -1, 'proc_open failed' ];
	}

	fclose( $pipes[0] );
	fclose( $pipes[1] );
	$stderr = (string) stream_get_contents( $pipes[2] );
	fclose( $pipes[2] );
	$exit_code = proc_close( $proc );

	return [ $exit_code, $stderr ];
}
