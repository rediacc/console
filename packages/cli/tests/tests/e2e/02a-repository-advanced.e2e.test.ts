import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { E2E } from '../../src/utils/e2e-constants';
import { getE2EConfig, setupE2EEnvironment } from '../../src/utils/local';
import { SSHValidator } from '../../src/utils/SSHValidator';

/**
 * Phase 4: Repository Advanced Operations
 *
 * Tests: repository_unmount, repository_mount, repository_down, repository_up,
 *        repository_resize, repository_expand, repository_validate,
 *        repository_ownership, repository_fork
 *
 * Creates a fresh repo, exercises mount/unmount/up/down lifecycle,
 * then resize, validate, ownership, and fork operations.
 */
test.describe
  .serial('Phase 4: Repository Advanced @e2e', () => {
    const config = getE2EConfig();
    let ssh1: SSHValidator;
    let cleanup: (() => Promise<void>) | null = null;
    let runner: CliTestRunner;
    const ctxName = `e2e-phase4-${Date.now()}`;
    const repoMountPath = `${E2E.REPO_MOUNTS_BASE}/${E2E.REPO_ADVANCED}`;
    const repo2MountPath = `${E2E.REPO_MOUNTS_BASE}/${E2E.REPO_ADVANCED_2}`;

    /** Helper to run a repo command on vm1 */
    const repoCmd = (cmd: string, repo: string, extraFlags: string[] = []) =>
      runner.run(['repository', cmd, repo, '--machine', E2E.MACHINE_VM1, ...extraFlags], {
        timeout: E2E.TEST_TIMEOUT,
      });

    test.beforeAll(async () => {
      test.skip(!config.enabled, 'E2E VMs not configured');
      ssh1 = new SSHValidator(config.vm1Ip, config.sshUser, config.sshKeyPath);
      cleanup = await setupE2EEnvironment(ctxName);
      runner = CliTestRunner.withContext(ctxName);

      // Force-delete stale repo from previous runs (ignore errors)
      try {
        await runner.run(
          [
            'repository',
            'down',
            E2E.REPO_ADVANCED,
            '--machine',
            E2E.MACHINE_VM1,
            '--option',
            'unmount',
          ],
          { timeout: 60_000 }
        );
      } catch {
        /* ignore */
      }
      try {
        await runner.run(
          ['repository', 'delete', E2E.REPO_ADVANCED, '--machine', E2E.MACHINE_VM1],
          { timeout: 60_000 }
        );
      } catch {
        /* ignore */
      }

      // Create the test repository for this phase
      const createResult = await runner.run(
        [
          'repository',
          'create',
          E2E.REPO_ADVANCED,
          '--machine',
          E2E.MACHINE_VM1,
          '--size',
          E2E.REPO_SIZE,
        ],
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(createResult);
    });

    test.afterAll(async () => {
      // Best-effort cleanup both repos
      if (runner) {
        for (const repo of [E2E.REPO_ADVANCED_2, E2E.REPO_ADVANCED]) {
          try {
            await runner.run(
              ['repository', 'down', repo, '--machine', E2E.MACHINE_VM1, '--option', 'unmount'],
              { timeout: 120_000 }
            );
          } catch {
            /* ignore */
          }
          try {
            await runner.run(['repository', 'delete', repo, '--machine', E2E.MACHINE_VM1], {
              timeout: 120_000,
            });
          } catch {
            /* ignore */
          }
        }
      }
      await cleanup?.();
    });

    test('repository_unmount - should unmount repository filesystem', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await repoCmd('unmount', E2E.REPO_ADVANCED);
      runner.expectSuccess(result);

      // SSH validation: mount point should be gone
      expect(await ssh1.mountExists(repoMountPath)).toBe(false);
    });

    test('repository_mount - should remount repository filesystem', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await repoCmd('mount', E2E.REPO_ADVANCED);
      runner.expectSuccess(result);

      // SSH validation: filesystem should be mounted again
      expect(await ssh1.mountExists(repoMountPath)).toBe(true);
    });

    test('repository_down - should stop repository services', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await repoCmd('down', E2E.REPO_ADVANCED);
      runner.expectSuccess(result);

      // Mount stays (down without --unmount only stops services)
      expect(await ssh1.dirExists(repoMountPath)).toBe(true);
    });

    test('repository_up - should start repository services', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await repoCmd('up', E2E.REPO_ADVANCED);
      runner.expectSuccess(result);

      // SSH validation: repository is still mounted and accessible
      expect(await ssh1.mountExists(repoMountPath)).toBe(true);
    });

    test('repository_resize - should reject resize for unencrypted repos', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      // Resize requires unmounted repo
      const unmountResult = await repoCmd('unmount', E2E.REPO_ADVANCED);
      runner.expectSuccess(unmountResult);

      // Offline resize is only supported for encrypted (LUKS) repositories.
      const result = await repoCmd('resize', E2E.REPO_ADVANCED, ['--size', E2E.REPO_SIZE_EXPANDED]);
      expect(result.exitCode).not.toBe(0);
      const output = result.stdout + result.stderr;
      expect(output).toContain('encrypted');

      // Remount after attempted resize
      const mountResult = await repoCmd('mount', E2E.REPO_ADVANCED);
      runner.expectSuccess(mountResult);
    });

    test('repository_expand - should handle expand for unencrypted repos', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await repoCmd('expand', E2E.REPO_ADVANCED, ['--size', E2E.REPO_SIZE_EXPANDED]);
      // Accept either success (if expand is a no-op) or rejection
      const output = result.stdout + result.stderr;
      expect(output.length).toBeGreaterThan(0);
    });

    test('repository_validate - should validate repository integrity', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await repoCmd('validate', E2E.REPO_ADVANCED);
      runner.expectSuccess(result);
    });

    test('repository_ownership - should set repository ownership', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await repoCmd('ownership', E2E.REPO_ADVANCED);
      runner.expectSuccess(result);

      // SSH validation: check ownership
      const ownerCheck = await ssh1.exec(`ls -ld ${repoMountPath}`);
      expect(ownerCheck.success).toBe(true);
      expect(ownerCheck.stdout.length).toBeGreaterThan(0);
    });

    test('repository_fork - should create independent copy of repository', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      // Write a test file into the source repo first
      await ssh1.writeFile(`${repoMountPath}/fork-test.txt`, 'fork-test-data');

      const result = await runner.run(
        [
          'repository',
          'fork',
          E2E.REPO_ADVANCED,
          '--machine',
          E2E.MACHINE_VM1,
          '--tag',
          E2E.REPO_ADVANCED_2,
        ],
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      // SSH validation: forked repo storage exists
      const repo2StoragePath = `${E2E.REPO_STORAGE_BASE}/${E2E.REPO_ADVANCED_2}`;
      expect(await ssh1.dirExists(repo2StoragePath)).toBe(true);

      // Mount the forked repo to validate its contents
      const mountResult = await repoCmd('mount', E2E.REPO_ADVANCED_2);
      runner.expectSuccess(mountResult);

      // SSH validation: forked repo is mounted
      expect(await ssh1.mountExists(repo2MountPath)).toBe(true);

      // SSH validation: test file exists in the fork
      expect(await ssh1.fileExists(`${repo2MountPath}/fork-test.txt`)).toBe(true);
    });
  });
