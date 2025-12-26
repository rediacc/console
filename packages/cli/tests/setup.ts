import { afterAll, beforeAll } from 'vitest';
import { logout } from './helpers/cli.js';
import { getConfig, setTestAccount } from './helpers/config.js';
import {
  generateTestAccount,
  registerAndActivate,
  type TestAccount,
} from './helpers/registration.js';

/**
 * Global test setup for integration tests
 *
 * This file runs before all tests to:
 * 1. Register a fresh company/user for this test run
 * 2. Activate the account with code 111111 (CI_MODE)
 * 3. Login with the new credentials
 *
 * This ensures tests have a clean environment and can perform CRUD operations freely.
 *
 * NOTE: Set SKIP_TEST_SETUP=1 to skip this setup (for unit tests that don't need API).
 */

let testAccount: TestAccount;
let setupComplete = false;

beforeAll(async () => {
  // Skip setup if explicitly disabled (for unit tests)
  if (process.env.SKIP_TEST_SETUP === '1') {
    return;
  }

  const config = getConfig();

  // eslint-disable-next-line no-console -- Test setup logging
  console.log(`\n[Setup] Testing against: ${config.apiUrl}`);

  // Generate and register a fresh test account
  testAccount = generateTestAccount();
  // eslint-disable-next-line no-console -- Test setup logging
  console.log(`[Setup] Registering: ${testAccount.email}`);

  try {
    await registerAndActivate(testAccount);
    // Store the account in config for use by login helper
    setTestAccount(testAccount);
    setupComplete = true;
    // eslint-disable-next-line no-console -- Test setup logging
    console.log('[Setup] Registration and login complete\n');
  } catch (error) {
    console.error('[Setup] Registration failed:', error);
    throw error;
  }
});

afterAll(async () => {
  // Skip teardown if setup was skipped
  if (!setupComplete) {
    return;
  }

  // Logout after all tests
  await logout();
  // eslint-disable-next-line no-console -- Test teardown logging
  console.log('\n[Teardown] Logged out');
});

export { testAccount };
