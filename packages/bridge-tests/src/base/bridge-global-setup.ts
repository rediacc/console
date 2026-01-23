import * as fs from 'node:fs';
import * as path from 'node:path';
import { FullConfig } from '@playwright/test';
import {
  CEPH_HEALTH_RETRY_MS,
  CEPH_HEALTH_TIMEOUT_MS,
  DEFAULT_DATASTORE_PATH,
  RENET_SETUP_TIMEOUT_MS,
} from '../constants';
import { getOpsManager } from '../utils/bridge/OpsManager';
import { InfrastructureManager } from '../utils/infrastructure/InfrastructureManager';

/**
 * Ensure .env file exists by copying from .env.example if not present.
 */
function ensureEnvFile() {
  const e2eDir = path.resolve(__dirname, '..', '..');
  const envPath = path.join(e2eDir, '.env');
  const envExamplePath = path.join(e2eDir, '.env.example');

  if (fs.existsSync(envPath) || !fs.existsSync(envExamplePath)) {
    return;
  }

  // eslint-disable-next-line no-console
  console.log('Creating .env from .env.example...');
  fs.copyFileSync(envExamplePath, envPath);
  // eslint-disable-next-line no-console
  console.log('Created .env file');
}

/**
 * Wait for Ceph cluster health check
 */
async function waitForCephHealth(opsManager: ReturnType<typeof getOpsManager>) {
  // eslint-disable-next-line no-console
  console.log('');
  // eslint-disable-next-line no-console
  console.log('Step 1b: Waiting for Ceph cluster health...');
  const healthTimeoutMs = CEPH_HEALTH_TIMEOUT_MS;
  const retryIntervalMs = CEPH_HEALTH_RETRY_MS;
  const startedAt = Date.now();
  let attempt = 0;

  while (Date.now() - startedAt < healthTimeoutMs) {
    attempt += 1;
    const healthResult = await opsManager.runOpsCommand(['ceph', 'health'], [], 120000);
    if (healthResult.code === 0) {
      // eslint-disable-next-line no-console
      console.log(`  ✓ Ceph cluster is healthy (attempt ${attempt})`);
      return;
    }

    if (Date.now() - startedAt >= healthTimeoutMs) {
      throw new Error(`Ceph health check failed: ${healthResult.stderr}`);
    }

    // eslint-disable-next-line no-console
    console.log(
      `  ! Ceph not healthy yet (attempt ${attempt}). Retrying in ${Math.round(retryIntervalMs / 1000)}s...`
    );
    await new Promise((resolve) => {
      setTimeout(resolve, retryIntervalMs);
    });
  }
}

/**
 * Run renet setup on ALL VMs (bridge + workers)
 * This installs Docker and other dependencies on fresh base images.
 */
async function setupAllVMs(opsManager: ReturnType<typeof getOpsManager>) {
  console.warn('');
  console.warn('Step 3: Running renet setup on ALL VMs (bridge + workers)...');

  // Get all VM IPs (bridge + workers)
  const bridgeIp = opsManager.getBridgeVMIp();
  const workerIps = opsManager.getWorkerVMIps();
  const allVmIps = [bridgeIp, ...workerIps];

  for (const ip of allVmIps) {
    const vmType = ip === bridgeIp ? 'bridge' : 'worker';
    console.warn(`  Setting up ${vmType} VM at ${ip}...`);
    const result = await opsManager.executeOnVM(ip, 'sudo renet setup', RENET_SETUP_TIMEOUT_MS);
    if (result.code === 0) {
      console.warn(`  ✓ Setup completed on ${ip} (${vmType})`);
    } else {
      // Fail fast - subsequent steps depend on setup being successful (Docker installed)
      throw new Error(
        `Setup failed on ${ip} (${vmType}): exit code ${result.code}\nstderr: ${result.stderr}\nstdout: ${result.stdout}`
      );
    }
  }
}

/**
 * Verify all VMs with retry logic
 */
async function verifyVMsWithRetry(
  opsManager: ReturnType<typeof getOpsManager>,
  infra: InfrastructureManager
) {
  console.warn('');
  console.warn('Step 4: Verifying all VMs are ready...');
  try {
    await opsManager.verifyAllVMsReady();
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (message.includes('(renet not installed)')) {
      // eslint-disable-next-line no-console
      console.log(
        'Renet missing on one or more VMs; re-deploying renet and retrying verification...'
      );
      await infra.ensureRenetOnVMs();
      await opsManager.verifyAllVMsReady();
    } else {
      throw err;
    }
  }
}

/**
 * Initialize datastores on worker VMs if workers are configured.
 */
async function initializeDatastoresIfNeeded(
  opsManager: ReturnType<typeof getOpsManager>,
  workerIps: string[]
) {
  if (workerIps.length > 0) {
    console.warn('');
    console.warn('Step 7: Initializing datastores on all worker VMs...');
    await opsManager.initializeAllDatastores('10G', DEFAULT_DATASTORE_PATH);
    console.warn('  ✓ All datastores initialized');
  } else {
    console.warn('');
    console.warn('Step 7: Skipping datastore initialization (Ceph-only mode, no workers)');
  }
}

/**
 * Deploy CRIU to worker VMs if workers are configured.
 */
async function deployCRIUIfNeeded(infra: InfrastructureManager, workerIps: string[]) {
  if (workerIps.length > 0) {
    console.warn('');
    console.warn('Step 8: Deploying CRIU to all worker VMs...');
    await infra.deployCRIUToAllVMs();
    console.warn('  ✓ CRIU deployed to all worker VMs');
  } else {
    console.warn('');
    console.warn('Step 8: Skipping CRIU deployment (Ceph-only mode, no workers)');
  }
}

/**
 * Start RustFS S3 storage on bridge VM.
 */
async function startRustFSStorage(opsManager: ReturnType<typeof getOpsManager>) {
  console.warn('');
  console.warn('Step 5: Starting RustFS S3 storage...');
  const rustfsResult = await opsManager.startRustFS();
  if (!rustfsResult.success) {
    throw new Error(`RustFS failed to start: ${rustfsResult.message}`);
  }
  console.warn(`  ✓ ${rustfsResult.message}`);
}

/**
 * Configure rclone on workers for RustFS access if workers exist.
 */
async function configureRustFSWorkersIfNeeded(
  opsManager: ReturnType<typeof getOpsManager>,
  workerIps: string[]
) {
  if (workerIps.length === 0) {
    return;
  }
  console.warn('');
  console.warn('Step 6: Configuring workers for RustFS access...');
  const configResult = await opsManager.configureRustFSWorkers();
  if (configResult.success) {
    console.warn(`  ✓ ${configResult.message}`);
  } else {
    console.warn(`  ! ${configResult.message} (non-fatal, tests may configure individually)`);
  }
}

/**
 * Write setup error to log file
 */
function writeSetupErrorLog(error: unknown) {
  try {
    const e2eDir = path.resolve(__dirname, '..', '..');
    const errorLogDir = path.join(e2eDir, 'reports', 'bridge-logs');
    const errorLogPath = path.join(errorLogDir, 'setup-error.txt');

    fs.mkdirSync(errorLogDir, { recursive: true });

    const errorMessage = error instanceof Error ? error.message : String(error);
    const errorStack = error instanceof Error ? error.stack : 'No stack trace';
    const timestamp = new Date().toISOString();

    const errorContent = [
      '================================================================================',
      'GLOBAL SETUP FAILED',
      '================================================================================',
      '',
      `Timestamp: ${timestamp}`,
      '',
      '----------------------------------------',
      'ERROR MESSAGE:',
      '----------------------------------------',
      errorMessage,
      '',
      '----------------------------------------',
      'STACK TRACE:',
      '----------------------------------------',
      errorStack,
      '',
      '================================================================================',
      'Tests did not run because setup failed.',
      'Fix the setup issue and run tests again.',
      '================================================================================',
    ].join('\n');

    fs.writeFileSync(errorLogPath, errorContent);
    console.error(`\nSetup error logged to: ${errorLogPath}`);
  } catch (writeError) {
    console.error(`\nFailed to write setup error log: ${writeError}`);
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
 * 2. Deploy renet binary to all VMs
 * 3. Run renet setup on ALL VMs (bridge + workers) to install Docker and dependencies
 * 4. Verify all VMs are ready (bridge + workers + ceph)
 * 5. Start RustFS S3 storage on bridge VM
 * 6. Configure rclone on workers for RustFS access
 * 7. Initialize datastores on worker VMs
 * 8. Deploy CRIU to worker VMs
 *
 * RENET BINARY:
 * The renet binary must be available before running tests. In CI, it's pre-extracted
 * from the Docker image. Locally, build with: cd renet && ./go dev
 *
 * NOTE: Ceph provisioning is automatically handled by `ops up` when VM_CEPH_NODES is configured.
 * Do NOT call provisionCeph() separately as this causes duplicate provisioning conflicts.
 */
async function bridgeGlobalSetup(_config: FullConfig) {
  ensureEnvFile();

  /* eslint-disable no-console */
  console.log('');
  console.log('='.repeat(60));
  console.log('Bridge Test Setup (SSH Mode)');
  console.log('='.repeat(60));
  /* eslint-enable no-console */

  const opsManager = getOpsManager();
  const infra = new InfrastructureManager();

  try {
    // Step 1: Soft reset VMs (mandatory - no skip option)
    // eslint-disable-next-line no-console
    console.log('');
    // eslint-disable-next-line no-console
    console.log('Step 1: Performing VM soft reset...');
    const resetResult = await opsManager.resetVMs();

    if (!resetResult.success) {
      throw new Error('VM reset failed - cannot proceed with tests');
    }
    // eslint-disable-next-line no-console
    console.log(`  ✓ VM reset completed in ${(resetResult.duration / 1000).toFixed(1)}s`);

    // Note: Ceph provisioning is automatically handled by ops up when VM_CEPH_NODES is configured
    const cephNodes = opsManager.getCephVMIps();
    if (cephNodes.length > 0) {
      await waitForCephHealth(opsManager);
    }

    // Step 2: Build renet and deploy to all VMs
    // eslint-disable-next-line no-console
    console.log('');
    // eslint-disable-next-line no-console
    console.log('Step 2: Building and deploying renet...');
    await infra.ensureInfrastructure();
    // eslint-disable-next-line no-console
    console.log('  ✓ Renet deployed to all VMs');

    // Step 3: Run renet setup on ALL VMs (bridge + workers) to install Docker and dependencies
    // This is required for fresh base images that don't have Docker pre-installed
    await setupAllVMs(opsManager);

    // Step 4: Verify all VMs are ready
    await verifyVMsWithRetry(opsManager, infra);

    // Step 5: Start RustFS S3 storage on bridge VM (mandatory for storage tests)
    await startRustFSStorage(opsManager);

    // Step 6: Configure rclone on workers for RustFS access (if workers exist)
    const workerIps = opsManager.getWorkerVMIps();
    await configureRustFSWorkersIfNeeded(opsManager, workerIps);

    // Step 7: Initialize datastores on all worker VMs
    await initializeDatastoresIfNeeded(opsManager, workerIps);

    // Step 8: Deploy CRIU to all worker VMs
    await deployCRIUIfNeeded(infra, workerIps);

    /* eslint-disable no-console */
    console.log('');
    console.log('='.repeat(60));
    console.log('All VMs ready for SSH-based test execution');
    console.log('='.repeat(60));
    console.log('');
    /* eslint-enable no-console */
  } catch (error) {
    console.error('');
    console.error('='.repeat(60));
    console.error('Setup failed:', error);
    console.error('='.repeat(60));

    writeSetupErrorLog(error);
    throw error;
  }
}

export default bridgeGlobalSetup;
