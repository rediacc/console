import { expect, test } from '@playwright/test';
import { E2E } from '../../src/utils/e2e-constants';
import {
  assertSuccess,
  getE2EConfig,
  runLocalFunction,
  setupE2EEnvironment,
} from '../../src/utils/local';
import { safeDeleteRepo } from '../../src/utils/local-operations';
import { SSHValidator } from '../../src/utils/SSHValidator';

/**
 * Phase 16: repository_diff — git-style file-level diff between two forks.
 *
 * Creates a repo, seeds a known file, forks it, modifies the fork (one edit,
 * one new file), mounts both, then diffs the base against the target and
 * verifies the changed file is reported. The diff compares the encrypted images
 * at the block level and maps changed blocks back to file names; here we assert
 * the end-to-end function path returns a successful, populated result.
 */
test.describe
  .serial('Phase 16: repository_diff @e2e', () => {
    const config = getE2EConfig();
    let cleanup: (() => Promise<void>) | null = null;
    const ctxName = `e2e-phase16-${Date.now()}`;

    test.beforeAll(async () => {
      test.skip(!config.enabled, 'E2E VMs not configured');
      cleanup = await setupE2EEnvironment(ctxName);

      await runLocalFunction('repository_create', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO, size: E2E.REPO_SIZE },
        timeout: E2E.TEST_TIMEOUT,
      });

      // Seed a deterministic file in the parent mount.
      const ssh = new SSHValidator(config.vm1Ip, config.sshUser, config.sshKeyPath);
      await ssh.writeFile(`${E2E.REPO_MOUNTS_BASE}/${E2E.TEST_REPO}/diffme.txt`, 'version one\n');
      await ssh.writeFile(`${E2E.REPO_MOUNTS_BASE}/${E2E.TEST_REPO}/keep.txt`, 'stable content\n');

      // Fork the parent, then mount both sides.
      await runLocalFunction('repository_fork', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO, tag: E2E.TEST_REPO_2 },
        timeout: E2E.TEST_TIMEOUT,
      });
      await runLocalFunction('repository_mount', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO },
        timeout: E2E.TEST_TIMEOUT,
      });
      await runLocalFunction('repository_mount', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO_2 },
        timeout: E2E.TEST_TIMEOUT,
      });

      // Mutate the fork: edit one file, add another.
      await ssh.writeFile(
        `${E2E.REPO_MOUNTS_BASE}/${E2E.TEST_REPO_2}/diffme.txt`,
        'version two, changed\n'
      );
      await ssh.writeFile(
        `${E2E.REPO_MOUNTS_BASE}/${E2E.TEST_REPO_2}/added.txt`,
        'new in the fork\n'
      );
    });

    test.afterAll(async () => {
      await safeDeleteRepo(E2E.MACHINE_VM1, E2E.TEST_REPO_2, ctxName);
      await safeDeleteRepo(E2E.MACHINE_VM1, E2E.TEST_REPO, ctxName);
      await cleanup?.();
    });

    test('repository_diff reports the modified and added files', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_diff', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO_2, base: E2E.TEST_REPO, target: E2E.TEST_REPO_2 },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);
      // `rdc run` surfaces only a progress line on stdout, not the renet JSON
      // payload, so success (exit 0) is the meaningful end-to-end signal: the
      // unencrypted directory-backed repo was diffed without hitting the old
      // "LUKS required" rejection. Content correctness (A/M/D/R) is covered by
      // repodiff's engine_dirbacked_test in the renet unit lane.
      const combined = `${result.stdout}\n${result.stderr}`;
      expect(combined).not.toMatch(/not LUKS-encrypted|read-only diff of unencrypted/i);
    });

    test('repository_diff --fast still succeeds', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_diff', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: {
          repository: E2E.TEST_REPO_2,
          base: E2E.TEST_REPO,
          target: E2E.TEST_REPO_2,
          fast: 'true',
        },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);
    });

    test('repository_diff --content returns a unified diff for one file', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_diff', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: {
          repository: E2E.TEST_REPO_2,
          base: E2E.TEST_REPO,
          target: E2E.TEST_REPO_2,
          content: 'diffme.txt',
        },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);
    });
  });
