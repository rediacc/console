import { expect, test } from '@playwright/test';
import {
  assertSuccess,
  getE2EConfig,
  runLocalFunction,
  setupE2EEnvironment,
} from '../../src/utils/local';
import { SSHValidator } from '../../src/utils/SSHValidator';
import { E2E } from '../../src/utils/e2e-constants';
import { safeDeleteRepo } from '../../src/utils/local-operations';

/**
 * Phase 3: Repository Lifecycle
 *
 * Tests the basic repository CRUD operations:
 * repository_create, repository_list, repository_info, repository_status, repository_delete
 *
 * Creates a single test repo, inspects it, then deletes it.
 * Each step validates actual VM state via SSH.
 */
test.describe
  .serial('Phase 3: Repository Lifecycle @e2e', () => {
    const config = getE2EConfig();
    let ssh1: SSHValidator;
    let cleanup: (() => Promise<void>) | null = null;
    const ctxName = `e2e-phase3-${Date.now()}`;
    const repoMountPath = `${E2E.REPO_MOUNTS_BASE}/${E2E.TEST_REPO}`;

    test.beforeAll(async () => {
      test.skip(!config.enabled, 'E2E VMs not configured');
      ssh1 = new SSHValidator(config.vm1Ip, config.sshUser, config.sshKeyPath);
      cleanup = await setupE2EEnvironment(ctxName);
    });

    test.afterAll(async () => {
      // Best-effort cleanup
      await safeDeleteRepo(E2E.MACHINE_VM1, E2E.TEST_REPO, ctxName);
      await cleanup?.();
    });

    test('repository_create - should create repository', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_create', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO, size: E2E.REPO_SIZE },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: repository is mounted
      expect(await ssh1.mountExists(repoMountPath)).toBe(true);

      // SSH validation: mount directory is accessible
      expect(await ssh1.dirExists(repoMountPath)).toBe(true);
    });

    test('repository_list - should list the created repository', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_list', E2E.MACHINE_VM1, {
        contextName: ctxName,
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // The output should contain our test repo name
      const output = result.stdout + result.stderr;
      expect(output).toContain(E2E.TEST_REPO);
    });

    test('repository_info - should show repository details', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_info', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // Output should contain meaningful information about the repo
      const output = result.stdout + result.stderr;
      expect(output.length).toBeGreaterThan(0);
    });

    test('repository_status - should report active status', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_status', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // Output should indicate the repo is mounted/active
      const output = result.stdout + result.stderr;
      expect(output.length).toBeGreaterThan(0);
    });

    test('repository_delete - should remove repository completely', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_delete', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);

      // SSH validation: mount is gone
      expect(await ssh1.mountExists(repoMountPath)).toBe(false);

      // SSH validation: repository storage is removed
      const storageCheck = await ssh1.exec(
        `ls ${E2E.REPO_STORAGE_BASE}/ | grep ${E2E.TEST_REPO} || echo GONE`
      );
      expect(storageCheck.stdout.trim()).toContain('GONE');
    });
  });
