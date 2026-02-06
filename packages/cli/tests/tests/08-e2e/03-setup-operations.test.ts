import { expect, test } from '@playwright/test';
import {
  assertSuccess,
  getE2EConfig,
  runLocalFunction,
  setupE2EEnvironment,
} from '../../src/utils/local';
import { SSHValidator } from '../../src/utils/SSHValidator';
import { E2E } from '../../src/utils/e2e-constants';

/**
 * Phase 2: Setup Operations
 *
 * Runs `setup` on vm1 and vm2 to prepare the machines for all subsequent tests.
 * This installs the datastore, Docker, BTRFS/LUKS tools, rsync, etc.
 *
 * Must run after Phase 1 (which uninstalls renet) to re-establish a working state.
 * Removes existing setup markers to force a fresh setup with datastore initialization.
 */
test.describe.serial('Phase 2: Setup Operations @e2e', () => {
  const config = getE2EConfig();
  let ssh1: SSHValidator;
  let ssh2: SSHValidator;
  let cleanup: (() => Promise<void>) | null = null;
  const ctxName = `e2e-phase2-${Date.now()}`;

  // Setup marker path matches renet's SetupMarkerPath(7111) = /var/lib/rediacc/setup_7111_completed
  const SETUP_MARKER = '/var/lib/rediacc/setup_7111_completed';

  test.beforeAll(async () => {
    test.skip(!config.enabled, 'E2E VMs not configured');
    ssh1 = new SSHValidator(config.vm1Ip, config.sshUser, config.sshKeyPath);
    ssh2 = new SSHValidator(config.vm2Ip, config.sshUser, config.sshKeyPath);
    cleanup = await setupE2EEnvironment(ctxName);

    // Remove setup markers to force fresh setup with datastore initialization.
    // This is necessary because setup is idempotent and skips datastore creation
    // if the marker already exists from a previous provisioning run.
    await ssh1.exec(`sudo rm -f ${SETUP_MARKER}`);
    if (config.vm2Ip) {
      await ssh2.exec(`sudo rm -f ${SETUP_MARKER}`);
    }
  });

  test.afterAll(async () => {
    await cleanup?.();
  });

  test('setup on vm1 - should prepare machine with datastore and tools', async () => {
    test.skip(!config.enabled, 'E2E not configured');
    test.setTimeout(E2E.SETUP_TIMEOUT);

    const result = await runLocalFunction('setup', E2E.MACHINE_VM1, {
      contextName: ctxName,
      timeout: E2E.SETUP_TIMEOUT,
    });
    assertSuccess(result);

    // SSH validation: datastore directory exists
    expect(await ssh1.dirExists(E2E.DATASTORE_PATH)).toBe(true);

    // SSH validation: BTRFS tools installed
    expect(await ssh1.commandExists('btrfs')).toBe(true);

    // SSH validation: Docker is running
    expect(await ssh1.serviceActive('docker')).toBe(true);

    // SSH validation: LUKS tools installed
    expect(await ssh1.commandExists('cryptsetup')).toBe(true);

    // SSH validation: rsync installed (needed for backups)
    expect(await ssh1.commandExists('rsync')).toBe(true);
  });

  test('setup on vm2 - should prepare second machine', async () => {
    test.skip(!config.enabled || !config.vm2Ip, 'E2E not configured or VM2 not available');
    test.setTimeout(E2E.SETUP_TIMEOUT);

    const result = await runLocalFunction('setup', E2E.MACHINE_VM2, {
      contextName: ctxName,
      timeout: E2E.SETUP_TIMEOUT,
    });
    assertSuccess(result);

    // SSH validation: datastore directory exists on vm2
    expect(await ssh2.dirExists(E2E.DATASTORE_PATH)).toBe(true);

    // SSH validation: BTRFS tools installed
    expect(await ssh2.commandExists('btrfs')).toBe(true);

    // SSH validation: Docker is running
    expect(await ssh2.serviceActive('docker')).toBe(true);

    // SSH validation: LUKS tools installed
    expect(await ssh2.commandExists('cryptsetup')).toBe(true);

    // SSH validation: rsync installed
    expect(await ssh2.commandExists('rsync')).toBe(true);
  });
});
