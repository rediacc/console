/**
 * Test configuration constants
 *
 * Central location for test environment defaults.
 * These can be overridden via environment variables.
 */

/**
 * Default API URL for testing
 * Override with REDIACC_TEST_API_URL environment variable
 */
export const DEFAULT_TEST_API_URL = 'https://draft-profits-speeches-antivirus.trycloudflare.com';

/**
 * Default timeout for CLI commands in milliseconds
 * Override with REDIACC_TEST_TIMEOUT environment variable
 */
export const DEFAULT_TEST_TIMEOUT = 30000;

/**
 * Email domain used for test account registration
 */
export const TEST_EMAIL_DOMAIN = 'rediacc.local';
