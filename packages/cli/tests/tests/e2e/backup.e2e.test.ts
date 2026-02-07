import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { E2E } from '../../src/utils/e2e-constants';
import { getE2EConfig, setupE2EEnvironment } from '../../src/utils/local';
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
    let runner: CliTestRunner;
    const ctxName = `e2e-phase7-${Date.now()}`;
    const repoMountPath = `${E2E.REPO_MOUNTS_BASE}/${E2E.REPO_BACKUP}`;
    let originalChecksum: string;
    let secondChecksum: string;

    test.beforeAll(async () => {
      test.skip(!config.enabled || !config.vm2Ip, 'E2E VMs not configured or VM2 not available');
      ssh1 = new SSHValidator(config.vm1Ip, config.sshUser, config.sshKeyPath);
      ssh2 = new SSHValidator(config.vm2Ip, config.sshUser, config.sshKeyPath);
      cleanup = await setupE2EEnvironment(ctxName);
      runner = CliTestRunner.withContext(ctxName);
    });

    test.afterAll(async () => {
      // Cleanup repos on both VMs
      if (runner) {
        for (const machine of [E2E.MACHINE_VM1, E2E.MACHINE_VM2]) {
          try {
            await runner.run(
              ['repository', 'down', E2E.REPO_BACKUP, '--machine', machine, '--option', 'unmount'],
              { timeout: 120_000 }
            );
          } catch {
            /* ignore */
          }
          try {
            await runner.run(['repository', 'delete', E2E.REPO_BACKUP, '--machine', machine], {
              timeout: 120_000,
            });
          } catch {
            /* ignore */
          }
        }
      }
      await cleanup?.();
    });

    test('setup - create repos and test data on both VMs', async () => {
      test.skip(!config.enabled || !config.vm2Ip, 'E2E not configured');
      test.setTimeout(E2E.SETUP_TIMEOUT);

      // Force-delete stale repos from previous runs (ignore errors)
      for (const machine of [E2E.MACHINE_VM1, E2E.MACHINE_VM2]) {
        try {
          await runner.run(
            ['repository', 'down', E2E.REPO_BACKUP, '--machine', machine, '--option', 'unmount'],
            { timeout: 60_000 }
          );
        } catch {
          /* ignore */
        }
        try {
          await runner.run(['repository', 'delete', E2E.REPO_BACKUP, '--machine', machine], {
            timeout: 60_000,
          });
        } catch {
          /* ignore */
        }
      }

      // Create repo on vm1
      const createResult1 = await runner.run(
        [
          'repository',
          'create',
          E2E.REPO_BACKUP,
          '--machine',
          E2E.MACHINE_VM1,
          '--size',
          E2E.REPO_SIZE,
        ],
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(createResult1);

      // Write a test file (10MB) to vm1 repo
      await ssh1.createTestFile(`${repoMountPath}/testfile.bin`, 10);
      originalChecksum = await ssh1.fileChecksum(`${repoMountPath}/testfile.bin`);
      expect(originalChecksum.length).toBeGreaterThan(0);

      // Create repo on vm2 (backup target)
      const createResult2 = await runner.run(
        [
          'repository',
          'create',
          E2E.REPO_BACKUP,
          '--machine',
          E2E.MACHINE_VM2,
          '--size',
          E2E.REPO_SIZE,
        ],
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(createResult2);
    });

    test('backup_push - should push repository to second machine', async () => {
      test.skip(!config.enabled || !config.vm2Ip, 'E2E not configured');
      test.setTimeout(E2E.SETUP_TIMEOUT);

      const extraMachineEntry = `${E2E.MACHINE_VM2}:${config.vm2Ip}:${config.sshUser}`;

      const result = await runner.run(
        [
          'backup',
          'push',
          '--repository',
          E2E.REPO_BACKUP,
          '--machine',
          E2E.MACHINE_VM1,
          '--destination-type',
          'machine',
          '--to',
          E2E.MACHINE_VM2,
          '--dest',
          E2E.REPO_BACKUP,
          '--extra-machine',
          extraMachineEntry,
        ],
        { timeout: E2E.SETUP_TIMEOUT }
      );
      runner.expectSuccess(result);

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

      const result = await runner.run(
        [
          'backup',
          'push',
          '--repository',
          E2E.REPO_BACKUP,
          '--machine',
          E2E.MACHINE_VM1,
          '--destination-type',
          'machine',
          '--to',
          E2E.MACHINE_VM2,
          '--dest',
          E2E.REPO_BACKUP,
          '--extra-machine',
          extraMachineEntry,
        ],
        { timeout: E2E.SETUP_TIMEOUT }
      );
      runner.expectSuccess(result);

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

      const result = await runner.run(
        [
          'backup',
          'pull',
          '--repository',
          E2E.REPO_BACKUP,
          '--machine',
          E2E.MACHINE_VM1,
          '--source-type',
          'machine',
          '--from',
          E2E.MACHINE_VM2,
          '--extra-machine',
          extraMachineEntry,
        ],
        { timeout: E2E.SETUP_TIMEOUT }
      );
      runner.expectSuccess(result);

      // SSH validation: files should be restored on vm1 with matching checksums
      const vm1Checksum1 = await ssh1.fileChecksum(`${repoMountPath}/testfile.bin`);
      const vm1Checksum2 = await ssh1.fileChecksum(`${repoMountPath}/testfile2.bin`);
      expect(vm1Checksum1).toBe(originalChecksum);
      expect(vm1Checksum2).toBe(secondChecksum);
    });
  });
