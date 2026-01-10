import { cleanupGlobalState, loadGlobalState } from './globalState.js';
import { getApiUrl } from '../constants.js';
import { AccountManager } from '../utils/AccountManager.js';
import type { FullConfig } from '@playwright/test';

/**
 * Global teardown for CLI tests.
 *
 * Cleanup:
 * 1. Logout from master context
 * 2. Delete master test context
 * 3. Clean up state file
 */
async function cliGlobalTeardown(_config: FullConfig): Promise<void> {
  console.warn('');
  console.warn('='.repeat(60));
  console.warn('CLI Test Teardown');
  console.warn('='.repeat(60));

  let masterContext: string | undefined;

  try {
    const state = loadGlobalState();
    masterContext = state.contextName;
  } catch {
    console.warn('No master context to clean up (setup may have failed)');
    cleanupGlobalState();
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

  // Clean up state file
  cleanupGlobalState();

  console.warn('');
  console.warn('='.repeat(60));
  console.warn('CLI Test Teardown Complete');
  console.warn('='.repeat(60));
}

export default cliGlobalTeardown;
