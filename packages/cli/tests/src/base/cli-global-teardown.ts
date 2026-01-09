import type { FullConfig } from "@playwright/test";
import { AccountManager } from "../utils/AccountManager.js";
import { getApiUrl } from "../constants.js";

/**
 * Global teardown for CLI tests.
 *
 * Cleanup:
 * 1. Logout from master context
 * 2. Delete master test context
 */
async function cliGlobalTeardown(_config: FullConfig): Promise<void> {
  console.log("");
  console.log("=".repeat(60));
  console.log("CLI Test Teardown");
  console.log("=".repeat(60));

  const masterContext = process.env.CLI_MASTER_CONTEXT;

  if (!masterContext) {
    console.log("No master context to clean up (setup may have failed)");
    return;
  }

  try {
    const accountManager = new AccountManager(getApiUrl());
    await accountManager.cleanupContext(masterContext);

    console.log(`  Cleaned up context: ${masterContext}`);
  } catch (error) {
    // Log but don't fail - teardown errors shouldn't affect test results
    console.error(`  Teardown error (non-fatal): ${error}`);
  }

  console.log("");
  console.log("=".repeat(60));
  console.log("CLI Test Teardown Complete");
  console.log("=".repeat(60));
}

export default cliGlobalTeardown;
