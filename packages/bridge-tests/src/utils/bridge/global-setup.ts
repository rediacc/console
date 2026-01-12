import { getOpsManager } from './OpsManager';

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
  // eslint-disable-next-line no-console
  console.log('\n============================================================');
  // eslint-disable-next-line no-console
  console.log('Bridge Test Global Setup');
  // eslint-disable-next-line no-console
  console.log('============================================================');
  // eslint-disable-next-line no-console
  console.log('');

  const opsManager = getOpsManager();

  // Check current VM status
  await checkVMStatus(opsManager);

  // Verify renet is available on all worker VMs
  await verifyRenetInstallation(opsManager);

  // Start RustFS S3 storage on bridge VM for storage tests
  await startRustFSStorage(opsManager);

  // eslint-disable-next-line no-console
  console.log('\n============================================================\n');
}

async function checkVMStatus(opsManager: ReturnType<typeof getOpsManager>): Promise<void> {
  // eslint-disable-next-line no-console
  console.log('Checking VM status...');
  const { ready, status } = await opsManager.areAllVMsReady();

  // eslint-disable-next-line no-console
  console.log('\nVM Status:');
  for (const [ip, vmStatus] of status) {
    const statusIcon = vmStatus.reachable && vmStatus.sshReady ? '✓' : '✗';
    // eslint-disable-next-line no-console
    console.log(`  ${statusIcon} ${ip}: reachable=${vmStatus.reachable}, ssh=${vmStatus.sshReady}`);
  }

  if (ready) {
    // eslint-disable-next-line no-console
    console.log('\nAll VMs are already running and ready!');
    return;
  }

  await startVMs(opsManager);
}

async function startVMs(opsManager: ReturnType<typeof getOpsManager>): Promise<void> {
  // eslint-disable-next-line no-console
  console.log('\nStarting VMs using ops scripts...');

  const result = await opsManager.ensureVMsRunning();

  if (!result.success) {
    console.error(`\nERROR: ${result.message}`);
    // eslint-disable-next-line no-console
    console.log('============================================================\n');
    throw new Error(`Failed to start VMs: ${result.message}`);
  }

  // eslint-disable-next-line no-console
  console.log(`\n${result.message}`);
  if (result.wasStarted) {
    // eslint-disable-next-line no-console
    console.log('VMs were started by this test run');
  }
}

async function verifyRenetInstallation(
  opsManager: ReturnType<typeof getOpsManager>
): Promise<void> {
  // eslint-disable-next-line no-console
  console.log('\nVerifying renet installation on worker VMs...');
  const workerIPs = opsManager.getWorkerVMIps();

  for (const ip of workerIPs) {
    const hasRenet = await opsManager.isRenetInstalledOnVM(ip);
    if (hasRenet) {
      const version = await opsManager.getRenetVersionOnVM(ip);
      // eslint-disable-next-line no-console, custom/no-hardcoded-nullish-defaults
      console.log(`  ✓ ${ip}: renet installed (${version ?? 'unknown version'})`);
    } else {
      console.error(`\nERROR: renet NOT found on ${ip}`);
      // eslint-disable-next-line no-console
      console.log('============================================================\n');
      throw new Error(`renet not installed on VM ${ip}`);
    }
  }
}

async function startRustFSStorage(opsManager: ReturnType<typeof getOpsManager>): Promise<void> {
  // eslint-disable-next-line no-console
  console.log('\nStarting RustFS S3 storage on bridge VM...');
  const rustfsResult = await opsManager.startRustFS();
  if (rustfsResult.success) {
    // eslint-disable-next-line no-console
    console.log(`  ✓ ${rustfsResult.message}`);
  } else {
    // RustFS is optional - storage tests will skip if not available
    // eslint-disable-next-line no-console
    console.log(`  ⚠ ${rustfsResult.message} (storage tests will be skipped)`);
  }
}

export default globalSetup;
