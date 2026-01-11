/**
 * Test/CI credentials - NEVER use in production
 * These values must match the middleware seed data
 */
export const TEST_CREDENTIALS = {
  /** Default admin email for development/CI */
  ADMIN_EMAIL: 'admin@rediacc.io',

  /** Default admin password for development/CI */
  ADMIN_PASSWORD: 'admin',

  /** CI activation code - only works when CI=true */
  CI_ACTIVATION_CODE: '111111',

  /** Test email domain for generated accounts */
  TEST_EMAIL_DOMAIN: 'rediacc.local',
} as const;

/** Environment variable names for credentials */
export const CREDENTIAL_ENV_VARS = {
  TEST_USER_EMAIL: 'TEST_USER_EMAIL',
  TEST_USER_PASSWORD: 'TEST_USER_PASSWORD',
  ADMIN_USER_EMAIL: 'ADMIN_USER_EMAIL',
  ADMIN_USER_PASSWORD: 'ADMIN_USER_PASSWORD',
  SYSTEM_ADMIN_EMAIL: 'SYSTEM_ADMIN_EMAIL',
  SYSTEM_ADMIN_PASSWORD: 'SYSTEM_ADMIN_PASSWORD',
  TEST_VERIFICATION_CODE: 'TEST_VERIFICATION_CODE',
} as const;
