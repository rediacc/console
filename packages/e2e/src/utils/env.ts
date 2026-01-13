import { TEST_CREDENTIALS } from '@rediacc/shared';

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
 * Get VM env var with fallback to defaults in test mode
 */
export function getVMEnvVar(name: string): string | undefined {
  const value = process.env[name];
  if (value) return value;

  if (isTestEnv()) {
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

export function isTestEnv(): boolean {
  return (
    process.env.E2E_TEST_MODE === 'true' ||
    process.env.E2E_TEST_MODE === '1' ||
    process.env.DEV_ENV === 'true' ||
    process.env.DEV_ENV === '1'
  );
}

export function requireEnvVar(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} environment variable is required`);
  }
  return value;
}

/**
 * Get env var with fallback to shared defaults (for test mode)
 */
export function getEnvVarWithDefault(name: string): string {
  const value = process.env[name];
  if (value) return value;

  if (name === 'TEST_VERIFICATION_CODE') {
    return TEST_CREDENTIALS.CI_ACTIVATION_CODE;
  }

  throw new Error(`${name} environment variable is required`);
}
