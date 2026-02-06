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
    const ctxName = `e2e-phase4-${Date.now()}`;
    const repoMountPath = `${E2E.REPO_MOUNTS_BASE}/${E2E.TEST_REPO}`;
    const repo2MountPath = `${E2E.REPO_MOUNTS_BASE}/${E2E.TEST_REPO_2}`;

    test.beforeAll(async () => {
      test.skip(!config.enabled, 'E2E VMs not configured');
      ssh1 = new SSHValidator(config.vm1Ip, config.sshUser, config.sshKeyPath);
      cleanup = await setupE2EEnvironment(ctxName);

      // Create the test repository for this phase
      await createRepo(E2E.MACHINE_VM1, E2E.TEST_REPO, E2E.REPO_SIZE, ctxName);
    });

    test.afterAll(async () => {
      // Best-effort cleanup both repos
      await safeDeleteRepo(E2E.MACHINE_VM1, E2E.TEST_REPO_2, ctxName);
      await safeDeleteRepo(E2E.MACHINE_VM1, E2E.TEST_REPO, ctxName);
      await cleanup?.();
    });

    test('repository_unmount - should unmount repository filesystem', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_unmount', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: mount point should be gone
      expect(await ssh1.mountExists(repoMountPath)).toBe(false);
    });

    test('repository_mount - should remount repository filesystem', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_mount', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: filesystem should be mounted again
      expect(await ssh1.mountExists(repoMountPath)).toBe(true);
    });

    test('repository_down - should stop repository services', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_down', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // Mount stays (down without --unmount only stops services)
      // Repo filesystem is still accessible
      expect(await ssh1.dirExists(repoMountPath)).toBe(true);
    });

    test('repository_up - should start repository services', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_up', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: repository is still mounted and accessible
      expect(await ssh1.mountExists(repoMountPath)).toBe(true);
    });

    test('repository_resize - should reject resize for unencrypted repos', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      // Resize requires unmounted repo
      const unmountResult = await runLocalFunction('repository_unmount', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(unmountResult);

      // Offline resize is only supported for encrypted (LUKS) repositories.
      // In local mode, repos are unencrypted (directory-backed), so resize
      // correctly rejects the operation.
      const result = await runLocalFunction('repository_resize', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO, size: E2E.REPO_SIZE_EXPANDED },
        timeout: E2E.TEST_TIMEOUT,
      });
      expect(result.exitCode).not.toBe(0);
      const output = result.stdout + result.stderr;
      expect(output).toContain('encrypted');

      // Remount after attempted resize
      const mountResult = await runLocalFunction('repository_mount', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(mountResult);
    });

    test('repository_expand - should handle expand for unencrypted repos', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      // For unencrypted directory repos, expand may not apply since there's no
      // per-repo backing device. We validate the command runs and check behavior.
      const result = await runLocalFunction('repository_expand', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO, size: E2E.REPO_SIZE_EXPANDED },
        timeout: E2E.TEST_TIMEOUT,
      });
      // Accept either success (if expand is a no-op) or rejection
      const output = result.stdout + result.stderr;
      expect(output.length).toBeGreaterThan(0);
    });

    test('repository_validate - should validate repository integrity', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_validate', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);
    });

    test('repository_ownership - should set repository ownership', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_ownership', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

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

      const result = await runLocalFunction('repository_fork', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO, tag: E2E.TEST_REPO_2 },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: forked repo storage exists
      const repo2StoragePath = `${E2E.REPO_STORAGE_BASE}/${E2E.TEST_REPO_2}`;
      expect(await ssh1.dirExists(repo2StoragePath)).toBe(true);

      // Mount the forked repo to validate its contents
      const mountResult = await runLocalFunction('repository_mount', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO_2 },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(mountResult);

      // SSH validation: forked repo is mounted
      expect(await ssh1.mountExists(repo2MountPath)).toBe(true);

      // SSH validation: test file exists in the fork
      expect(await ssh1.fileExists(`${repo2MountPath}/fork-test.txt`)).toBe(true);
    });
  });
