import * as fs from "fs";
import * as path from "path";
import { fileURLToPath } from "url";
import type { FullConfig } from "@playwright/test";
import { CliTestRunner } from "../utils/CliTestRunner.js";
import { AccountManager } from "../utils/AccountManager.js";
import { getApiUrl } from "../constants.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Ensure .env file exists by copying from .env.example if not present.
 */
function ensureEnvFile(): void {
  const testsDir = path.resolve(__dirname, "../..");
  const envPath = path.join(testsDir, ".env");
  const envExamplePath = path.join(testsDir, ".env.example");

  if (!fs.existsSync(envPath) && fs.existsSync(envExamplePath)) {
    console.log("Creating .env from .env.example...");
    fs.copyFileSync(envExamplePath, envPath);
    console.log("Created .env file");
  }
}

/**
 * Global setup for CLI tests.
 *
 * Setup sequence:
 * 1. Ensure .env file exists
 * 2. Validate CLI is working (--version)
 * 3. Create master test context (register + activate + login)
 * 4. Verify default infrastructure (region, bridge)
 * 5. Store credentials in environment for test access
 *
 * Tests access the master context via:
 * - process.env.CLI_MASTER_CONTEXT
 * - process.env.CLI_MASTER_EMAIL
 * - process.env.CLI_MASTER_PASSWORD
 */
async function cliGlobalSetup(_config: FullConfig): Promise<void> {
  // Ensure .env file exists
  ensureEnvFile();

  console.log("");
  console.log("=".repeat(60));
  console.log("CLI Test Setup");
  console.log("=".repeat(60));

  const apiUrl = getApiUrl();
  console.log(`\nTarget API: ${apiUrl}`);

  try {
    // Step 1: Validate CLI is working
    console.log("\nStep 1: Validating CLI...");
    const runner = new CliTestRunner({ apiUrl });

    const versionResult = await runner.version();
    if (!versionResult.success) {
      throw new Error(`CLI not working: ${runner.getErrorMessage(versionResult)}`);
    }
    console.log(`  CLI version: ${versionResult.stdout.trim()}`);

    // Step 2: Create master test context
    console.log("\nStep 2: Creating master test context...");
    const accountManager = new AccountManager(apiUrl);
    const masterAccount = await accountManager.createMasterContext();

    // Store credentials in environment for test access
    process.env.CLI_MASTER_CONTEXT = masterAccount.contextName;
    process.env.CLI_MASTER_EMAIL = masterAccount.email;
    process.env.CLI_MASTER_PASSWORD = masterAccount.password;

    console.log(`  Context: ${masterAccount.contextName}`);
    console.log(`  Email: ${masterAccount.email}`);

    // Step 3: Verify default infrastructure
    console.log("\nStep 3: Verifying default infrastructure...");
    await accountManager.verifyDefaultInfrastructure(masterAccount.contextName);
    console.log("  Default infrastructure verified");

    console.log("");
    console.log("=".repeat(60));
    console.log("CLI Test Setup Complete");
    console.log("=".repeat(60));
    console.log("");

  } catch (error) {
    console.error("");
    console.error("=".repeat(60));
    console.error("Setup failed:", error);
    console.error("=".repeat(60));

    // Write setup error to reports for visibility
    try {
      const testsDir = path.resolve(__dirname, "../..");
      const errorLogDir = path.join(testsDir, "reports", "cli-logs");
      const errorLogPath = path.join(errorLogDir, "setup-error.txt");

      fs.mkdirSync(errorLogDir, { recursive: true });

      const errorMessage = error instanceof Error ? error.message : String(error);
      const errorStack = error instanceof Error ? error.stack : "No stack trace";
      const timestamp = new Date().toISOString();

      const errorContent = [
        "================================================================================",
        "GLOBAL SETUP FAILED",
        "================================================================================",
        "",
        `Timestamp: ${timestamp}`,
        `API URL: ${getApiUrl()}`,
        "",
        "----------------------------------------",
        "ERROR MESSAGE:",
        "----------------------------------------",
        errorMessage,
        "",
        "----------------------------------------",
        "STACK TRACE:",
        "----------------------------------------",
        errorStack ?? "N/A",
        "",
        "================================================================================",
        "Tests did not run because setup failed.",
        "Fix the setup issue and run tests again.",
        "================================================================================",
      ].join("\n");

      fs.writeFileSync(errorLogPath, errorContent);
      console.error(`\nSetup error logged to: ${errorLogPath}`);
    } catch (writeError) {
      console.error(`\nFailed to write setup error log: ${writeError}`);
    }

    throw error;
  }
}

export default cliGlobalSetup;
