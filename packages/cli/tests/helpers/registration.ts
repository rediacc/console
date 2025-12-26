import { randomBytes } from 'crypto';
import { getErrorMessage, runCli } from './cli.js';
import { getConfig } from './config.js';

export interface TestAccount {
  companyName: string;
  email: string;
  password: string;
}

/**
 * Generate a unique test account for this test run
 */
export function generateTestAccount(): TestAccount {
  const id = randomBytes(4).toString('hex');
  return {
    companyName: `TestCo-${id}`,
    email: `test-${id}@rediacc.local`,
    password: `TestPass${id}!`,
  };
}

/**
 * Register a new company and activate the account
 * Uses activation code 111111 which works when backend is in CI_MODE
 */
export async function registerAndActivate(account: TestAccount): Promise<void> {
  const config = getConfig();

  // 1. Register
  const registerResult = await runCli([
    'auth',
    'register',
    '--company',
    account.companyName,
    '-e',
    account.email,
    '-p',
    account.password,
    '--endpoint',
    config.apiUrl,
  ]);

  if (!registerResult.success) {
    throw new Error(`Registration failed: ${getErrorMessage(registerResult)}`);
  }

  // 2. Activate with 111111 (CI_MODE activation code)
  const activateResult = await runCli([
    'auth',
    'activate',
    '-e',
    account.email,
    '-p',
    account.password,
    '--code',
    '111111',
    '--endpoint',
    config.apiUrl,
  ]);

  if (!activateResult.success) {
    throw new Error(`Activation failed: ${getErrorMessage(activateResult)}`);
  }

  // 3. Login
  const loginResult = await runCli([
    'login',
    '-e',
    account.email,
    '-p',
    account.password,
    '--endpoint',
    config.apiUrl,
  ]);

  if (!loginResult.success) {
    throw new Error(`Login failed: ${getErrorMessage(loginResult)}`);
  }
}
