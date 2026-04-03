/**
 * Version information for @rediacc/cli package.
 *
 * Build-time: __CLI_VERSION__ is injected via esbuild --define (same pattern as Go -ldflags).
 * Dev-time:   Falls back to DEV_VERSION (updated by bump.sh).
 */
declare const __CLI_VERSION__: string | undefined;
const DEV_VERSION = '0.7.8';
export const VERSION: string = typeof __CLI_VERSION__ !== 'undefined' && __CLI_VERSION__ !== '' ? __CLI_VERSION__ : DEV_VERSION;
