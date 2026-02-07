import { expect, test } from '@playwright/test';
import { E2E } from '../../src/utils/e2e-constants';
import {
  assertSuccess,
  getE2EConfig,
  runLocalFunction,
  setupE2EEnvironment,
} from '../../src/utils/local';
import { createRepo, safeDeleteRepo } from '../../src/utils/local-operations';
import { SSHValidator } from '../../src/utils/SSHValidator';

/**
 * Phase 7: Backup Operations
 *
 * Tests backup_push and backup_pull between two VMs.
 *
 * Requires:
 * - Two VMs (vm1 and vm2) with repositories set up
 * - CLI --extra-machine support for multi-machine vault
 *
 * Flow:
 * 1. Create repo on vm1, write test file
 * 2. Create repo on vm2 (backup target)
 * 3. backup_push from vm1 to vm2
 * 4. Verify file exists on vm2 with matching checksum
 * 5. Write second file on vm1, incremental backup_push
 * 6. backup_pull from vm2 back to vm1
 * 7. Verify files restored
 */
test.describe
  .serial('Phase 7: Backup Operations @e2e', () => {
    const config = getE2EConfig();
    let ssh1: SSHValidator;
    let ssh2: SSHValidator;
    let cleanup: (() => Promise<void>) | null = null;
    const ctxName = `e2e-phase7-${Date.now()}`;
    const repoMountPath = `${E2E.REPO_MOUNTS_BASE}/${E2E.TEST_REPO}`;
    let originalChecksum: string;
    let secondChecksum: string;

    test.beforeAll(async () => {
      test.skip(!config.enabled || !config.vm2Ip, 'E2E VMs not configured or VM2 not available');
      ssh1 = new SSHValidator(config.vm1Ip, config.sshUser, config.sshKeyPath);
      ssh2 = new SSHValidator(config.vm2Ip, config.sshUser, config.sshKeyPath);
      cleanup = await setupE2EEnvironment(ctxName);
    });

    test.afterAll(async () => {
      // Cleanup repos on both VMs
      await safeDeleteRepo(E2E.MACHINE_VM1, E2E.TEST_REPO, ctxName);
      await safeDeleteRepo(E2E.MACHINE_VM2, E2E.TEST_REPO, ctxName);
      await cleanup?.();
    });

    test('setup - create repos and test data on both VMs', async () => {
      test.skip(!config.enabled || !config.vm2Ip, 'E2E not configured');
      test.setTimeout(E2E.SETUP_TIMEOUT);

      // Create repo on vm1
      await createRepo(E2E.MACHINE_VM1, E2E.TEST_REPO, E2E.REPO_SIZE, ctxName);

      // Write a test file (10MB) to vm1 repo
      await ssh1.createTestFile(`${repoMountPath}/testfile.bin`, 10);
      originalChecksum = await ssh1.fileChecksum(`${repoMountPath}/testfile.bin`);
      expect(originalChecksum.length).toBeGreaterThan(0);

      // Create repo on vm2 (backup target)
      await createRepo(E2E.MACHINE_VM2, E2E.TEST_REPO, E2E.REPO_SIZE, ctxName);
    });

    test('backup_push - should push repository to second machine', async () => {
      test.skip(!config.enabled || !config.vm2Ip, 'E2E not configured');
      test.setTimeout(E2E.SETUP_TIMEOUT);

      const extraMachineEntry = `${E2E.MACHINE_VM2}:${config.vm2Ip}:${config.sshUser}`;

      const result = await runLocalFunction('backup_push', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: {
          repository: E2E.TEST_REPO,
          destinationType: 'machine',
          to: E2E.MACHINE_VM2,
          dest: E2E.TEST_REPO,
        },
        extraMachines: [extraMachineEntry],
        timeout: E2E.SETUP_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: file should exist on vm2 with matching checksum
      const vm2Checksum = await ssh2.fileChecksum(`${repoMountPath}/testfile.bin`);
      expect(vm2Checksum).toBe(originalChecksum);
    });

    test('backup_push incremental - should push changes to second machine', async () => {
      test.skip(!config.enabled || !config.vm2Ip, 'E2E not configured');
      test.setTimeout(E2E.SETUP_TIMEOUT);

      // Write second file on vm1
      await ssh1.createTestFile(`${repoMountPath}/testfile2.bin`, 5);
      secondChecksum = await ssh1.fileChecksum(`${repoMountPath}/testfile2.bin`);

      const extraMachineEntry = `${E2E.MACHINE_VM2}:${config.vm2Ip}:${config.sshUser}`;

      const result = await runLocalFunction('backup_push', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: {
          repository: E2E.TEST_REPO,
          destinationType: 'machine',
          to: E2E.MACHINE_VM2,
          dest: E2E.TEST_REPO,
        },
        extraMachines: [extraMachineEntry],
        timeout: E2E.SETUP_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: both files should exist on vm2 with matching checksums
      const vm2Checksum1 = await ssh2.fileChecksum(`${repoMountPath}/testfile.bin`);
      const vm2Checksum2 = await ssh2.fileChecksum(`${repoMountPath}/testfile2.bin`);
      expect(vm2Checksum1).toBe(originalChecksum);
      expect(vm2Checksum2).toBe(secondChecksum);
    });

    test('backup_pull - should pull repository from second machine', async () => {
      test.skip(!config.enabled || !config.vm2Ip, 'E2E not configured');
      test.setTimeout(E2E.SETUP_TIMEOUT);

      // Delete files on vm1 to verify pull restores them
      await ssh1.removeFile(`${repoMountPath}/testfile.bin`);
      await ssh1.removeFile(`${repoMountPath}/testfile2.bin`);

      // Verify files are gone on vm1
      expect(await ssh1.fileExists(`${repoMountPath}/testfile.bin`)).toBe(false);

      const extraMachineEntry = `${E2E.MACHINE_VM2}:${config.vm2Ip}:${config.sshUser}`;

      const result = await runLocalFunction('backup_pull', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: {
          repository: E2E.TEST_REPO,
          sourceType: 'machine',
          from: E2E.MACHINE_VM2,
        },
        extraMachines: [extraMachineEntry],
        timeout: E2E.SETUP_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: files should be restored on vm1 with matching checksums
      const vm1Checksum1 = await ssh1.fileChecksum(`${repoMountPath}/testfile.bin`);
      const vm1Checksum2 = await ssh1.fileChecksum(`${repoMountPath}/testfile2.bin`);
      expect(vm1Checksum1).toBe(originalChecksum);
      expect(vm1Checksum2).toBe(secondChecksum);
    });
  });
