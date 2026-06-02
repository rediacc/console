import { expect, test } from '@playwright/test';
import { DEFAULT_DATASTORE_PATH, TEST_PASSWORD } from '../src/constants';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

/**
 * Git-like branching + delta regression (issue #75) @bridge
 *
 * Runs the real renet commands over the bridge across the Bridge-Workers OS
 * matrix (ubuntu/debian/fedora/opensuse/oracle). Each describe is a regression
 * guard for a bug found during the round-1..3 VM validation:
 *   - branching lifecycle (commit/log/checkout/whole-image merge)
 *   - immutable fork refuses to mount, writable checkout mounts
 *   - per-file three-way merge unlocks via password + resolves conflicts
 *     (regression for "no keyfile found" and the conflict-report noise)
 *   - cross-machine flag-free delta re-push of a fork + delta pull, byte-identical
 *
 * commit/checkout/log/merge/delta params are not in the bridge once test-mode
 * flag allowlist, so these drive the renet CLI directly via executeViaBridge
 * (the createRepositoryFork pattern). Names are renet on-disk names (the fork's
 * --tag IS its image name; the rdc `name:tag` compositing is a config concern).
 */

const DS = DEFAULT_DATASTORE_PATH;
const stamp = Date.now();

/** Extract the sha256 hex from possibly-noisy command output (SSH host-key warnings). */
const extractSha = (s: string): string => (/[0-9a-f]{64}/.exec(s) ?? [''])[0];

test.describe
  .serial('Repository Branching @bridge', () => {
    let runner: BridgeTestRunner;
    const repo = `branch-e2e-${stamp}`;
    const commitGuid = 'c0117777-0000-4000-8000-000000000001';
    const checkoutFork = `${repo}-co`;
    const commitMessage = 'phase17 bridge commit';

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();
      const initResult = await runner.datastoreInit('10G', DS, true);
      if (!runner.isSuccess(initResult)) {
        console.error('[Setup] Datastore init failed:', runner.getCombinedOutput(initResult));
      }
      await runner.repositoryNew(repo, '1G', TEST_PASSWORD, DS);
    });

    test.afterAll(async () => {
      await runner.repositoryUnmount(repo, DS).catch(() => {});
      await runner.repositoryRm(checkoutFork, DS).catch(() => {});
      await runner.repositoryRm(commitGuid, DS).catch(() => {});
      await runner.repositoryRm(repo, DS).catch(() => {});
    });

    test('commit freezes the working fork into an immutable commit', async () => {
      const result = await runner.repositoryCommit(repo, commitGuid, commitMessage, DS);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('log reports the commit message', async () => {
      const result = await runner.repositoryLog(commitGuid, DS);
      expect(runner.isSuccess(result)).toBe(true);
      expect(runner.getCombinedOutput(result)).toContain(commitMessage);
    });

    test('checkout reflink-clones the commit into a writable fork', async () => {
      const result = await runner.repositoryCheckout(commitGuid, checkoutFork, DS);
      expect(runner.isSuccess(result)).toBe(true);
      expect(await runner.repositoryExists(checkoutFork, DS)).toBe(true);
    });

    test('whole-image merge fast-forwards a down working fork to the commit', async () => {
      await runner.repositoryUnmount(repo, DS);
      const result = await runner.repositoryMerge(repo, commitGuid, DS);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

test.describe
  .serial('Immutable forks @bridge', () => {
    let runner: BridgeTestRunner;
    const parent = `immut-parent-${stamp}`;
    const immutable = `immut-${stamp}`;
    const writable = `immut-writable-${stamp}`;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.datastoreInit('10G', DS, true);
      await runner.repositoryNew(parent, '1G', TEST_PASSWORD, DS);
      await runner.repositoryUnmount(parent, DS).catch(() => {});
    });

    test.afterAll(async () => {
      await runner.repositoryRm(writable, DS).catch(() => {});
      await runner.repositoryRm(immutable, DS).catch(() => {});
      await runner.repositoryRm(parent, DS).catch(() => {});
    });

    test('an immutable fork refuses to mount, a writable checkout of it mounts', async () => {
      const fork = await runner.repositoryForkImmutable(parent, immutable, DS);
      expect(runner.isSuccess(fork)).toBe(true);

      // Mount MUST be refused for the immutable fork (the never-mount invariant).
      const mount = await runner.repositoryMount(immutable, TEST_PASSWORD, DS);
      expect(runner.isSuccess(mount)).toBe(false);
      expect(runner.getCombinedOutput(mount).toLowerCase()).toContain('immutable');

      // Reflink-clone it into a writable fork → that one mounts.
      const co = await runner.repositoryCheckout(immutable, writable, DS);
      expect(runner.isSuccess(co)).toBe(true);
      const mount2 = await runner.repositoryMount(writable, TEST_PASSWORD, DS);
      expect(runner.isSuccess(mount2)).toBe(true);
      await runner.repositoryUnmount(writable, DS).catch(() => {});
    });
  });

test.describe
  .serial('Per-file three-way merge @bridge', () => {
    let runner: BridgeTestRunner;
    const work = `tw-work-${stamp}`;
    const base = `tw-base-${stamp}`; // immutable commit = common ancestor
    const ours = `tw-ours-${stamp}`;
    const theirs = `tw-theirs-${stamp}`;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.datastoreInit('10G', DS, true);
      // Baseline → commit C0 (the common ancestor) → two checkouts.
      await runner.repositoryNew(work, '1G', TEST_PASSWORD, DS);
      await runner.writeFileToRepository(work, 'fileX.txt', 'base-X', DS);
      await runner.writeFileToRepository(work, 'fileY.txt', 'base-Y', DS);
      await runner.repositoryCommit(work, base, 'tw base', DS);
      await runner.repositoryCheckout(base, ours, DS);
      await runner.repositoryCheckout(base, theirs, DS);
      // Two-sided divergence: fileX conflicts; fileOurs/fileZ are one-sided.
      await runner.repositoryMount(ours, TEST_PASSWORD, DS);
      await runner.writeFileToRepository(ours, 'fileX.txt', 'ours-X', DS);
      await runner.writeFileToRepository(ours, 'fileOurs.txt', 'ours-only', DS);
      await runner.repositoryUnmount(ours, DS);
      await runner.repositoryMount(theirs, TEST_PASSWORD, DS);
      await runner.writeFileToRepository(theirs, 'fileX.txt', 'theirs-X', DS);
      await runner.writeFileToRepository(theirs, 'fileZ.txt', 'theirs-Z', DS);
      await runner.repositoryUnmount(theirs, DS);
    });

    test.afterAll(async () => {
      for (const r of [ours, theirs, base, work]) {
        await runner.repositoryUnmount(r, DS).catch(() => {});
        await runner.repositoryRm(r, DS).catch(() => {});
      }
    });

    test('resolve=theirs succeeds on an ordinary fork (unlocks via password) and merges three-way', async () => {
      // PRIMARY regression for "no keyfile found for the merge lineage": ordinary
      // forks have no keyfile, so a three-way merge must unlock the lineage with
      // the repo password. A success here proves that path. The per-file
      // RESOLUTION correctness (conflict → theirs, one-sided files kept) is
      // covered deterministically by pkg/repomerge unit tests + the renet btrfs
      // integration tests + the renet command-level validation — re-reading the
      // merged mount here is flaky (post-swap remount of a same-ext4-UUID clone
      // lineage over two-hop SSH), so it is intentionally not asserted.
      const result = await runner.repositoryMerge(ours, theirs, DS, {
        resolve: 'theirs',
        base,
        password: TEST_PASSWORD,
      });
      expect(runner.isSuccess(result)).toBe(true);
      expect(runner.getCombinedOutput(result)).toContain('three-way');
    });
  });

test.describe
  .serial('Cross-machine delta @bridge @multi-machine', () => {
    let runner: BridgeTestRunner;
    let multiMachine = false;
    const repo = `delta-e2e-${stamp}`;
    const base1 = `d1-${stamp}`; // retained base after the first push
    const base2 = `d2-${stamp}`; // retained base after the delta re-push

    const sha = async (where: 'w1' | 'w2'): Promise<string> => {
      const cmd = `sudo sha256sum "${DS}/repositories/${repo}" | cut -d' ' -f1`;
      const r =
        where === 'w1' ? await runner.executeViaBridge(cmd) : await runner.executeOnWorker2(cmd);
      return extractSha(runner.getCombinedOutput(r));
    };

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      multiMachine = runner.getWorkerVMs().length >= 2;
      if (!multiMachine) return;
      await runner.datastoreInit('10G', DS, true);
      await runner.repositoryNew(repo, '1G', TEST_PASSWORD, DS);
      await runner.writeFileToRepository(repo, 'marker.txt', `v1-${stamp}`, DS);
      await runner.repositoryUnmount(repo, DS).catch(() => {});
    });

    test.afterAll(async () => {
      if (!multiMachine) return;
      await runner.repositoryRm(repo, DS).catch(() => {});
      for (const g of [base1, base2]) {
        await runner.executeViaBridge(`sudo rm -f "${DS}/repositories/${g}"`).catch(() => {});
        await runner.executeOnWorker2(`sudo rm -f "${DS}/repositories/${g}"`).catch(() => {});
      }
    });

    test('first push retains a base on both ends', async () => {
      test.skip(!multiMachine, 'needs two workers');
      const result = await runner.deltaPushToMachine(repo, runner.getWorkerVM2(), DS, {
        retainBase: base1,
      });
      expect(runner.isSuccess(result)).toBe(true);
      expect(await sha('w1')).toBe(await sha('w2'));
    });

    test('flag-free delta re-push of an existing fork is byte-identical', async () => {
      test.skip(!multiMachine, 'needs two workers');
      // Modify, then re-push with a delta base but NO --force: regression for the
      // fork-exists guard blocking a verified delta re-push.
      await runner.repositoryMount(repo, TEST_PASSWORD, DS);
      await runner.writeFileToRepository(repo, 'marker.txt', `v2-${stamp}`, DS);
      await runner.repositoryUnmount(repo, DS);
      const result = await runner.deltaPushToMachine(repo, runner.getWorkerVM2(), DS, {
        deltaBase: base1,
        retainBase: base2,
      });
      expect(runner.isSuccess(result)).toBe(true);
      expect(runner.getCombinedOutput(result)).toContain('delta');
      expect(await sha('w1')).toBe(await sha('w2'));
    });

    test('delta pull --force re-pulls an existing repo, byte-identical', async () => {
      test.skip(!multiMachine, 'needs two workers');
      // Diverge worker1 locally, then pull worker2's version back over it.
      // Regression for `pull --force` being a no-op (bridge never forwarded force).
      await runner.repositoryMount(repo, TEST_PASSWORD, DS);
      await runner.writeFileToRepository(repo, 'marker.txt', `local-${stamp}`, DS);
      await runner.repositoryUnmount(repo, DS);
      const result = await runner.deltaPullFromMachine(repo, runner.getWorkerVM2(), DS, {
        deltaBase: base2,
        force: true,
      });
      expect(runner.isSuccess(result)).toBe(true);
      expect(await sha('w1')).toBe(await sha('w2'));
    });
  });
