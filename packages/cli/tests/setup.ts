import { beforeAll, afterAll } from 'vitest';
import { logout } from './helpers/cli.js';
import { getConfig, setTestAccount } from './helpers/config.js';
import { generateTestAccount, registerAndActivate, type TestAccount } from './helpers/registration.js';

/**
 * Global test setup
 *
 * This file runs before all tests to:
 * 1. Register a fresh company/user for this test run
 * 2. Activate the account with code 111111 (CI_MODE)
 * 3. Login with the new credentials
 *
 * This ensures tests have a clean environment and can perform CRUD operations freely.
 */

let testAccount: TestAccount;

beforeAll(async () => {
  const config = getConfig();

  console.log(`\n[Setup] Testing against: ${config.apiUrl}`);

  // Generate and register a fresh test account
  testAccount = generateTestAccount();
  console.log(`[Setup] Registering: ${testAccount.email}`);

  try {
    await registerAndActivate(testAccount);
    // Store the account in config for use by login helper
    setTestAccount(testAccount);
    console.log('[Setup] Registration and login complete\n');
  } catch (error) {
    console.error('[Setup] Registration failed:', error);
    throw error;
  }
});

afterAll(async () => {
  // Logout after all tests
  await logout();
  console.log('\n[Teardown] Logged out');
});

export { testAccount };
