/**
 * E2E Test Constants
 *
 * These constants are inlined here because the e2e package cannot import from
 * @rediacc/shared/config due to module resolution issues (TypeScript project
 * references require the shared package to be built first, but typecheck runs
 * before build in CI).
 */

export const E2E_DEFAULTS = {
  MACHINE_NAME: 'machine-1',
  CPU_COUNT_STRING: '0',
} as const;

export const FILE_DEFAULTS = {
  PNG: 'png',
} as const;

export const TIMEOUT_DEFAULTS = {
  SCREENSHOT: 30000,
} as const;
