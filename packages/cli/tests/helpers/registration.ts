import { randomBytes } from 'crypto';
import { getErrorMessage, runCli } from './cli.js';
import { getConfig } from './config.js';
import { TEST_EMAIL_DOMAIN } from './constants.js';

export type SubscriptionPlan = 'COMMUNITY' | 'PROFESSIONAL' | 'BUSINESS' | 'ENTERPRISE';

export interface TestAccount {
  organizationName: string;
  email: string;
  password: string;
  contextName: string;
  plan?: SubscriptionPlan;
}

/**
 * Generate a unique test account for this test run
 * @param plan Optional subscription plan (defaults to COMMUNITY)
 */
export function generateTestAccount(plan?: SubscriptionPlan): TestAccount {
  const id = randomBytes(4).toString('hex');
  return {
    organizationName: `TestOrg-${id}`,
    email: `test-${id}@${TEST_EMAIL_DOMAIN}`,
    password: `TestPass${id}!`,
    contextName: `test-${id}`,
    plan,
  };
}

/**
 * Register a new organization and activate the account
 * Uses activation code 111111 which works when backend is in CI_MODE
 * @param account Test account with optional subscription plan
 */
export async function registerAndActivate(account: TestAccount): Promise<void> {
  const config = getConfig();

  // 1. Register
  const registerArgs = [
    'auth',
    'register',
    '--organization',
    account.organizationName,
    '-e',
    account.email,
    '-p',
    account.password,
    '--endpoint',
    config.apiUrl,
  ];

  // Add plan if specified
  if (account.plan) {
    registerArgs.push('--plan', account.plan);
  }

  const registerResult = await runCli(registerArgs);

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
