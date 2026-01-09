import { getApiUrl } from '../constants.js';
import { AccountManager } from '../utils/AccountManager.js';
import type { FullConfig } from '@playwright/test';

/**
 * Global teardown for CLI tests.
 *
 * Cleanup:
 * 1. Logout from master context
 * 2. Delete master test context
 */
async function cliGlobalTeardown(_config: FullConfig): Promise<void> {
  console.warn('');
  console.warn('='.repeat(60));
  console.warn('CLI Test Teardown');
  console.warn('='.repeat(60));

  const masterContext = process.env.CLI_MASTER_CONTEXT;

  if (!masterContext) {
    console.warn('No master context to clean up (setup may have failed)');
    return;
  }

  try {
    const accountManager = new AccountManager(getApiUrl());
    await accountManager.cleanupContext(masterContext);

    console.warn(`  Cleaned up context: ${masterContext}`);
  } catch (error) {
    // Log but don't fail - teardown errors shouldn't affect test results
    console.error(`  Teardown error (non-fatal): ${error}`);
  }

  console.warn('');
  console.warn('='.repeat(60));
  console.warn('CLI Test Teardown Complete');
  console.warn('='.repeat(60));
}

export default cliGlobalTeardown;
