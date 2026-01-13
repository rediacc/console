import { CREDENTIAL_ENV_VARS, TEST_CREDENTIALS } from '@rediacc/shared';

// Static VM network configuration (matches bridge-tests/OpsManager pattern)
export const VM_DEFAULTS = {
  NET_BASE: '192.168.111',
  WORKER_IDS: [11, 12],
  MACHINE_USER: 'muhammed',
} as const;

function getDefaultWorkerIPs(): string[] {
  return VM_DEFAULTS.WORKER_IDS.map((id) => `${VM_DEFAULTS.NET_BASE}.${id}`);
}

/**
 * Get VM env var with fallback to defaults in CI
 */
export function getVMEnvVar(name: string): string | undefined {
  const value = process.env[name];
  if (value) return value;

  if (process.env.CI === 'true') {
    switch (name) {
      case 'VM_WORKER_IPS':
        return getDefaultWorkerIPs().join(',');
      case 'VM_MACHINE_USER':
        return VM_DEFAULTS.MACHINE_USER;
      case 'VM_MACHINE_PASSWORD':
        return ''; // SSH key auth
    }
  }
  return undefined;
}

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
