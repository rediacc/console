import { CREDENTIAL_ENV_VARS, TEST_CREDENTIALS } from '@rediacc/shared';

export function requireEnvVar(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} environment variable is required`);
  }
  return value;
}

/**
 * Get env var with fallback to shared defaults (for CI mode)
 */
export function getEnvVarWithDefault(name: string): string {
  const value = process.env[name];
  if (value) return value;

  // CI mode fallbacks
  if (process.env.CI === 'true') {
    switch (name) {
      case CREDENTIAL_ENV_VARS.TEST_USER_EMAIL:
      case CREDENTIAL_ENV_VARS.ADMIN_USER_EMAIL:
      case CREDENTIAL_ENV_VARS.SYSTEM_ADMIN_EMAIL:
        return TEST_CREDENTIALS.ADMIN_EMAIL;
      case CREDENTIAL_ENV_VARS.TEST_USER_PASSWORD:
      case CREDENTIAL_ENV_VARS.ADMIN_USER_PASSWORD:
      case CREDENTIAL_ENV_VARS.SYSTEM_ADMIN_PASSWORD:
        return TEST_CREDENTIALS.ADMIN_PASSWORD;
      case CREDENTIAL_ENV_VARS.TEST_VERIFICATION_CODE:
        return TEST_CREDENTIALS.CI_ACTIVATION_CODE;
    }
  }

  throw new Error(`${name} environment variable is required`);
}
