import { afterAll, beforeAll, beforeEach } from 'vitest';
import { getErrorMessage, runCli } from './helpers/cli.js';
import { getConfig, getTestContextName, setTestAccount, setTestContextName } from './helpers/config.js';
import {
  generateTestAccount,
  registerAndActivate,
  type TestAccount,
} from './helpers/registration.js';

// Store setup error to fail tests explicitly instead of skipping
let setupError: Error | null = null;

/**
 * Verify that default infrastructure (region, bridge) was created.
 * This catches middleware bugs where organization setup fails silently.
 */
async function verifyDefaultInfrastructure(context: string): Promise<void> {
  // Verify default region exists
  const regionsResult = await runCli(['region', 'list'], { context });
  if (!regionsResult.success) {
    throw new Error(`Failed to list regions: ${getErrorMessage(regionsResult)}`);
  }
  const regions = regionsResult.json as { regionName: string }[];
  if (!Array.isArray(regions) || regions.length === 0) {
    throw new Error('No default region found after organization registration');
  }

  // Verify default bridge exists in the default region
  const defaultRegion = regions[0].regionName;
  const bridgesResult = await runCli(['bridge', 'list', '--region', defaultRegion], { context });
  if (!bridgesResult.success) {
    throw new Error(`Failed to list bridges: ${getErrorMessage(bridgesResult)}`);
  }
  const bridges = bridgesResult.json as { bridgeName: string }[];
  if (!Array.isArray(bridges) || bridges.length === 0) {
    throw new Error(
      `No default bridge found in region "${defaultRegion}" after organization registration`
    );
  }
}

/**
 * Global test setup for integration tests
 *
 * This file runs before all tests to:
 * 1. Register a fresh organization/user for this test run
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
    // Create isolated context for this test file (enables parallel execution)
    // Pass --api-url to avoid interactive prompt
    const createResult = await runCli([
      'context',
      'create',
      testAccount.contextName,
      '--api-url',
      config.apiUrl,
    ]);
    if (!createResult.success) {
      throw new Error(`Context creation failed: ${getErrorMessage(createResult)}`);
    }

    // Store context name for use by runCli (auto-injects --context flag)
    setTestContextName(testAccount.contextName);

    await registerAndActivate(testAccount);
    // Store the account in config for use by login helper
    setTestAccount(testAccount);

    // Verify default infrastructure was created (region, bridge)
    await verifyDefaultInfrastructure(testAccount.contextName);

    setupComplete = true;
    // eslint-disable-next-line no-console -- Test setup logging
    console.log(`[Setup] Registration complete (context: ${testAccount.contextName})\n`);
  } catch (error) {
    // Store error to fail tests explicitly in beforeEach (instead of skipping)
    setupError = error instanceof Error ? error : new Error(String(error));
    console.error('[Setup] Registration failed:', error);
  }
});

// Fail each test explicitly if setup failed (instead of skipping)
beforeEach(() => {
  if (process.env.SKIP_TEST_SETUP === '1') {
    return;
  }
  if (setupError) {
    throw setupError;
  }
});

afterAll(async () => {
  // Skip teardown if setup was skipped
  if (!setupComplete) {
    return;
  }

  const contextName = getTestContextName();

  // Logout after all tests
  await runCli(['logout']);

  // Delete the isolated test context to clean up
  if (contextName) {
    // Clear context name first so delete command uses "default"
    setTestContextName(null);
    await runCli(['context', 'delete', contextName, '--force']);
    // eslint-disable-next-line no-console -- Test teardown logging
    console.log(`\n[Teardown] Logged out and cleaned up context: ${contextName}`);
  }
});

export { testAccount };
