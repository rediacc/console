/**
 * CLI Test Constants
 *
 * Centralized configuration for CLI E2E tests.
 */

// Environment variable helpers
function getEnvOrDefault(key: string, defaultValue: string): string {
  return process.env[key] ?? defaultValue;
}

function _getEnvOrThrow(key: string): string {
  const value = process.env[key];
  if (!value) {
    throw new Error(`Required environment variable ${key} is not set`);
  }
  return value;
}

// =============================================================================
// API Configuration
// =============================================================================

/** Default API URL for local development */
export const DEFAULT_API_URL = 'http://localhost:7322/api';

/** Get configured API URL */
export function getApiUrl(): string {
  return getEnvOrDefault('CLI_API_URL', DEFAULT_API_URL);
}

// =============================================================================
// Test Credentials
// =============================================================================

/** Email domain for generated test accounts */
export const TEST_EMAIL_DOMAIN = 'rediacc.local';

/** Activation code for CI mode */
export const CI_ACTIVATION_CODE = '111111';

// =============================================================================
// Timeouts
// =============================================================================

/** Default CLI command timeout in milliseconds */
export const DEFAULT_CLI_TIMEOUT = 30000;

/** Get configured CLI timeout */
export function getCliTimeout(): number {
  const timeout = process.env.CLI_TIMEOUT;
  return timeout ? Number.parseInt(timeout, 10) : DEFAULT_CLI_TIMEOUT;
}

// =============================================================================
// Paths
// =============================================================================

/** Path to CLI bundle relative to cli package root */
export const CLI_BUNDLE_PATH = 'dist/cli-bundle.cjs';

// =============================================================================
// Test Context
// =============================================================================

/** Prefix for generated test context names */
export const TEST_CONTEXT_PREFIX = 'test-';

/** Prefix for generated test organization names */
export const TEST_ORG_PREFIX = 'TestOrg-';

// =============================================================================
// Feature Flags
// =============================================================================

/** Check if running in CI mode */
export function isCI(): boolean {
  return process.env.CI === 'true' || process.env.CI === '1';
}

/** Check if debug mode is enabled */
export function isDebug(): boolean {
  return process.env.DEBUG === 'true' || process.env.DEBUG === '1';
}
