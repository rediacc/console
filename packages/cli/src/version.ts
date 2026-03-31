/**
 * CLI version -- injected at build time via esbuild define.
 * Source of truth: git tags (e.g., v0.8.2).
 * Dev builds show '0.0.0-dev'.
 */
declare const __CLI_VERSION__: string;
export const VERSION: string =
  typeof __CLI_VERSION__ !== 'undefined' ? __CLI_VERSION__ : '0.0.0-dev';
