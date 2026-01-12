import * as fs from "fs";
import * as path from "path";
import { FullConfig } from "@playwright/test";
import { CEPH_HEALTH_RETRY_MS, CEPH_HEALTH_TIMEOUT_MS, DEFAULT_DATASTORE_PATH } from "../constants";
import { getOpsManager } from "../utils/bridge/OpsManager";
import { InfrastructureManager } from "../utils/infrastructure/InfrastructureManager";

/**
 * Ensure .env file exists by copying from .env.example if not present.
 */
function ensureEnvFile() {
  const e2eDir = path.resolve(__dirname, "..", "..");
  const envPath = path.join(e2eDir, ".env");
  const envExamplePath = path.join(e2eDir, ".env.example");

  if (!fs.existsSync(envPath) && fs.existsSync(envExamplePath)) {
    console.log("Creating .env from .env.example...");
    fs.copyFileSync(envExamplePath, envPath);
    console.log("Created .env file");
  }
}

/**
 * Global setup for bridge tests.
 *
 * EXECUTION MODEL: All tests run on VMs via SSH
 * Host → Bridge VM → SSH → Worker/Ceph VM → renet command
 *
 * Setup sequence:
 * 1. Soft reset VMs (ops up --force --parallel) - includes Ceph provisioning if enabled
 * 2. Build renet and deploy to all VMs
 * 3. Verify all VMs are ready (bridge + workers + ceph)
 *
 * CI MODE:
 * When CI=true and RENET_BINARY_PATH is set, the renet binary is expected to be
 * pre-extracted from the Docker image by the CI workflow. The setup will use this
 * pre-extracted binary instead of building from source.
 *
 * Expected CI workflow steps (before running tests):
 * 1. docker pull ghcr.io/rediacc/elite/bridge:latest
 * 2. Extract binary: docker cp container:/opt/renet/renet-linux-amd64 /tmp/renet
 * 3. Set RENET_BINARY_PATH=/tmp/renet
 *
 * NOTE: Ceph provisioning is handled by `ops up` when PROVISION_CEPH_CLUSTER=true.
 * Do NOT call provisionCeph() separately as this causes duplicate provisioning conflicts.
 */
async function bridgeGlobalSetup(_config: FullConfig) {
  // Ensure .env file exists
  ensureEnvFile();

  console.log("");
  console.log("=".repeat(60));
  console.log("Bridge Test Setup (SSH Mode)");
  console.log("=".repeat(60));

  const opsManager = getOpsManager();
  const infra = new InfrastructureManager();

  try {
    // Pre-build renet so ops up uses the latest binary (includes provisioning fixes)
    console.log("");
    console.log("Pre-building renet for ops up...");
    await infra.buildRenet();

    // Step 1: Soft reset VMs (mandatory - no skip option)
    console.log("");
    console.log("Step 1: Performing VM soft reset...");
    const resetResult = await opsManager.resetVMs();

    if (!resetResult.success) {
      throw new Error("VM reset failed - cannot proceed with tests");
    }
    console.log(`  ✓ VM reset completed in ${(resetResult.duration / 1000).toFixed(1)}s`);
    // Note: Ceph provisioning is handled by ops up when PROVISION_CEPH_CLUSTER=true
    const cephNodes = opsManager.getCephVMIps();
    if (cephNodes.length > 0) {
      console.log("");
      console.log("Step 1b: Waiting for Ceph cluster health...");
      const healthTimeoutMs = CEPH_HEALTH_TIMEOUT_MS;
      const retryIntervalMs = CEPH_HEALTH_RETRY_MS;
      const startedAt = Date.now();
      let attempt = 0;

      while (Date.now() - startedAt < healthTimeoutMs) {
        attempt += 1;
        const healthResult = await opsManager.runOpsCommand(["ceph", "health"], [], 120000);
        if (healthResult.code === 0) {
          console.log(`  ✓ Ceph cluster is healthy (attempt ${attempt})`);
          break;
        }

        if (Date.now() - startedAt >= healthTimeoutMs) {
          throw new Error(`Ceph health check failed: ${healthResult.stderr}`);
        }

        console.log(
          `  ! Ceph not healthy yet (attempt ${attempt}). Retrying in ${Math.round(retryIntervalMs / 1000)}s...`,
        );
        await new Promise((resolve) => setTimeout(resolve, retryIntervalMs));
      }
    }

    // Step 2: Build renet and deploy to all VMs
    console.log("");
    console.log("Step 2: Building and deploying renet...");
    await infra.ensureInfrastructure();
    console.log("  ✓ Renet deployed to all VMs");

    // Step 2b: Run renet setup on all worker VMs to create universal user (rediacc)
    // This is required for multi-machine operations (push/pull) that use sudo -u rediacc
    console.log("");
    console.log("Step 2b: Running renet setup on all worker VMs...");
    const workerIps = opsManager.getWorkerVMIps();
    for (const ip of workerIps) {
      const result = await opsManager.executeOnVM(ip, "sudo renet setup");
      if (result.code !== 0) {
        console.error(`  ✗ Setup failed on ${ip}: ${result.stderr}`);
      } else {
        console.log(`  ✓ Setup completed on ${ip}`);
      }
    }

    // Step 3: Verify all VMs are ready
    console.log("");
    console.log("Step 3: Verifying all VMs are ready...");
    try {
      await opsManager.verifyAllVMsReady();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (message.includes("(renet not installed)")) {
        console.log(
          "Renet missing on one or more VMs; re-deploying renet and retrying verification...",
        );
        await infra.ensureRenetOnVMs();
        await opsManager.verifyAllVMsReady();
      } else {
        throw err;
      }
    }

    // Step 4: Start RustFS S3 storage on bridge VM (mandatory for storage tests)
    console.log("");
    console.log("Step 4: Starting RustFS S3 storage...");
    const rustfsResult = await opsManager.startRustFS();
    if (rustfsResult.success) {
      console.log(`  ✓ ${rustfsResult.message}`);
    } else {
      throw new Error(`RustFS failed to start: ${rustfsResult.message}`);
    }

    // Step 5: Initialize datastores on all worker VMs
    console.log("");
    console.log("Step 5: Initializing datastores on all worker VMs...");
    await opsManager.initializeAllDatastores("10G", DEFAULT_DATASTORE_PATH);
    console.log("  ✓ All datastores initialized");

    // Step 6: Deploy CRIU to all worker VMs
    console.log("");
    console.log("Step 6: Deploying CRIU to all worker VMs...");
    await infra.deployCRIUToAllVMs();
    console.log("  ✓ CRIU deployed to all worker VMs");

    console.log("");
    console.log("=".repeat(60));
    console.log("All VMs ready for SSH-based test execution");
    console.log("=".repeat(60));
    console.log("");
  } catch (error) {
    console.error("");
    console.error("=".repeat(60));
    console.error("Setup failed:", error);
    console.error("=".repeat(60));

    // Write setup error to reports for visibility when tests fail during setup
    try {
      const e2eDir = path.resolve(__dirname, "..", "..");
      const errorLogDir = path.join(e2eDir, "reports", "bridge-logs");
      const errorLogPath = path.join(errorLogDir, "setup-error.txt");

      console.error(`\n[DEBUG] __dirname: ${__dirname}`);
      console.error(`[DEBUG] e2eDir: ${e2eDir}`);
      console.error(`[DEBUG] errorLogPath: ${errorLogPath}`);

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
        "",
        "----------------------------------------",
        "ERROR MESSAGE:",
        "----------------------------------------",
        errorMessage,
        "",
        "----------------------------------------",
        "STACK TRACE:",
        "----------------------------------------",
        errorStack,
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

export default bridgeGlobalSetup;
