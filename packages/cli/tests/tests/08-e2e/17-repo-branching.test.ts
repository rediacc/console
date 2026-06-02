import { expect, test } from '@playwright/test';
import { E2E } from '../../src/utils/e2e-constants';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import {
  assertSuccess,
  getE2EConfig,
  runLocalFunction,
  setupE2EEnvironment,
} from '../../src/utils/local';
import { safeDeleteRepo } from '../../src/utils/local-operations';

/**
 * Phase 17: git-like branching — repository_commit + repository_log.
 *
 * Creates a repo (left mounted), commits it into an immutable commit object,
 * then walks the commit DAG with repository_log. Asserts the commit succeeds
 * and the log reports the commit. The immutable commit refuses to mount
 * (validated at the renet layer and in 04-repository-lifecycle's immutable
 * coverage); here we assert the end-to-end commit/log function path.
 */
test.describe
  .serial('Phase 17: repository branching @e2e', () => {
    const config = getE2EConfig();
    let cleanup: (() => Promise<void>) | null = null;
    const ctxName = `e2e-phase17-${Date.now()}`;
    const commitGuid = `c0117777-0000-4000-8000-${Date.now().toString().slice(-12).padStart(12, '0')}`;

    test.beforeAll(async () => {
      test.skip(!config.enabled, 'E2E VMs not configured');
      cleanup = await setupE2EEnvironment(ctxName);

      await runLocalFunction('repository_create', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO, size: E2E.REPO_SIZE },
        timeout: E2E.TEST_TIMEOUT,
      });
    });

    test.afterAll(async () => {
      await safeDeleteRepo(E2E.MACHINE_VM1, commitGuid, ctxName);
      await safeDeleteRepo(E2E.MACHINE_VM1, E2E.TEST_REPO, ctxName);
      await cleanup?.();
    });

    test('repository_commit freezes the working fork into an immutable commit', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_commit', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO, tag: commitGuid, message: 'phase17 commit' },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);
    });

    test('repository_log walks the commit DAG', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_log', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: commitGuid },
        timeout: E2E.TEST_TIMEOUT,
        // debug streams renet's raw `-o json` stdout (the LogResult, incl. the commit
        // message) through to the captured CLI stdout. Without it `rdc run` uses the
        // step-detection stdout handler, which renders progress spinners and discards
        // the function's JSON payload, so the message never reaches result.stdout.
        debug: true,
      });
      assertSuccess(result);
      expect(result.stdout).toContain('phase17 commit');
    });

    test('repository_merge fast-forwards the working fork to a commit', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      // repository_create leaves the repo mounted, so the merge gate requires
      // --force to quiesce it first. Merge the commit back into the working fork.
      const result = await runLocalFunction('repository_merge', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO, from: commitGuid, force: 'true' },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);
    });

    test('repository_commit_meta reconstructs the commit mirror (cross-machine log sync)', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      // Rewriting the commit's own mirror from metadata is idempotent; this is the
      // path `repo push` invokes on a TARGET after a commit lands so `repo log`
      // works post-push without unlocking the (immutable) image.
      const result = await runLocalFunction('repository_commit_meta', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: commitGuid, message: 'phase17 commit' },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);
    });

    // gc/fsck are CLI-only (they orchestrate repository_list/repository_delete +
    // the config ref store); they have no renet bridge fn, so they are exercised
    // here through the rdc CLI rather than the bridge-tests harness.
    test('repo gc --dry-run reports unreachable commits without deleting', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);
      const runner = CliTestRunner.withContext(ctxName);
      // Dry-run is the default (no --apply); the immutable commit above is not
      // reachable from any branch, so it is listed but not deleted.
      const result = await runner.run(['repo', 'gc', '-m', E2E.MACHINE_VM1]);
      expect(result.exitCode).toBe(0);
      expect(await safeRepoExists(commitGuid, ctxName)).toBe(true); // dry-run kept it
    });

    test('repo fsck validates config refs against machine objects', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);
      const runner = CliTestRunner.withContext(ctxName);
      const result = await runner.run(['repo', 'fsck', '-m', E2E.MACHINE_VM1]);
      // fsck is read-only; exit 0 (no drift) or 1 (drift reported) are both valid.
      expect([0, 1]).toContain(result.exitCode);
      expect(`${result.stdout}${result.stderr}`).toMatch(/drift|orphan|dangling|clean/i);
    });
  });

/** Whether a repo image still exists on VM1 (used to assert gc dry-run kept it). */
async function safeRepoExists(repoGuid: string, ctxName: string): Promise<boolean> {
  const result = await runLocalFunction('repository_list', E2E.MACHINE_VM1, {
    contextName: ctxName,
    params: {},
    timeout: E2E.TEST_TIMEOUT,
    // debug streams renet's raw `-o json` stdout through to the captured CLI stdout;
    // without it `rdc run`'s step-detection handler discards the list payload and the
    // GUID check below would always be false. Same reason as the repository_log test.
    debug: true,
  });
  return `${result.stdout}`.includes(repoGuid);
}
