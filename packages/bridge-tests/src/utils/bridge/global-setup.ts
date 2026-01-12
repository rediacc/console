import { getOpsManager } from "./OpsManager";

/**
 * Global setup for bridge tests
 *
 * Always runs in full VM mode:
 * 1. Check if VMs are already running
 * 2. Start VMs if needed using ops scripts
 * 3. Wait for all VMs to be ready (ping + SSH)
 * 4. Verify renet is installed on worker VMs
 *
 * Throws error if VMs cannot be started or are not ready.
 */
async function globalSetup(): Promise<void> {
  console.log("\n============================================================");
  console.log("Bridge Test Global Setup");
  console.log("============================================================");
  console.log("");

  const opsManager = getOpsManager();

  // Check current VM status
  console.log("Checking VM status...");
  const { ready, status } = await opsManager.areAllVMsReady();

  console.log("\nVM Status:");
  for (const [ip, vmStatus] of status) {
    const statusIcon = vmStatus.reachable && vmStatus.sshReady ? "✓" : "✗";
    console.log(`  ${statusIcon} ${ip}: reachable=${vmStatus.reachable}, ssh=${vmStatus.sshReady}`);
  }

  if (ready) {
    console.log("\nAll VMs are already running and ready!");
  } else {
    // Start VMs using ops scripts
    console.log("\nStarting VMs using ops scripts...");

    const result = await opsManager.ensureVMsRunning();

    if (!result.success) {
      console.error(`\nERROR: ${result.message}`);
      console.log("============================================================\n");
      throw new Error(`Failed to start VMs: ${result.message}`);
    }

    console.log(`\n${result.message}`);
    if (result.wasStarted) {
      console.log("VMs were started by this test run");
    }
  }

  // Verify renet is available on all worker VMs
  console.log("\nVerifying renet installation on worker VMs...");
  const workerIPs = opsManager.getWorkerVMIps();

  for (const ip of workerIPs) {
    const hasRenet = await opsManager.isRenetInstalledOnVM(ip);
    if (hasRenet) {
      const version = await opsManager.getRenetVersionOnVM(ip);
      console.log(`  ✓ ${ip}: renet installed (${version ?? "unknown version"})`);
    } else {
      console.error(`\nERROR: renet NOT found on ${ip}`);
      console.log("============================================================\n");
      throw new Error(`renet not installed on VM ${ip}`);
    }
  }

  // Start RustFS S3 storage on bridge VM for storage tests
  console.log("\nStarting RustFS S3 storage on bridge VM...");
  const rustfsResult = await opsManager.startRustFS();
  if (rustfsResult.success) {
    console.log(`  ✓ ${rustfsResult.message}`);
  } else {
    // RustFS is optional - storage tests will skip if not available
    console.log(`  ⚠ ${rustfsResult.message} (storage tests will be skipped)`);
  }

  console.log("\n============================================================\n");
}

export default globalSetup;
