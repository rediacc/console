/**
 * Test credentials - NEVER use in production
 */
export const TEST_CREDENTIALS = {
  /**
   * Complex password for registering NEW test accounts
   * Meets requirements: 8+ chars, upper/lower, number, special char
   */
  TEST_PASSWORD: 'TestPass123!',

  /** Activation code for test mode (e2e/automation) */
  CI_ACTIVATION_CODE: '111111',

  /** Test email domain for generated accounts */
  TEST_EMAIL_DOMAIN: 'rediacc.local',
} as const;
