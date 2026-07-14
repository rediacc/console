import { expect, test } from '@playwright/test';
import { DEFAULT_DATASTORE_PATH } from '../src/constants';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

/**
 * Datastore Lifecycle Tests (bridge).
 *
 * TRANSLATED from the pre-P1 surface, not merely renamed. The datastore-centric
 * redesign DELETED the unnamed-datastore bridge verbs this file used to drive:
 *
 *   datastore_init    -> gone from the bridge. Laying down the machine's BASE pool
 *                        is now a root CLI step (`renet datastore init`), which the
 *                        harness performs in OpsManager during global setup — it is
 *                        not a per-test bridge dispatch any more.
 *   datastore_mount   -> datastore_attach <name>  (named registry)
 *   datastore_unmount -> datastore_detach <name>  (named registry)
 *
 * So the SUBJECT changed: a machine no longer has one implicit `/mnt/rediacc`
 * datastore that you init/mount/unmount by path — it has a REGISTRY of named
 * datastores you create/attach/detach, plus the base pool underneath them. The
 * lifecycle coverage is preserved against the surviving surface:
 *
 *   create -> attach -> validate -> expand -> detach -> delete
 *
 * `datastore_expand`, `datastore_resize`, `datastore_validate` and `datastore_status`
 * survive UNCHANGED: they act on the machine's base pool, identified by the DATASTORE
 * CONTEXT (`renet functions once --datastore-path <p>`), not by a function param. That
 * context is what each command's RequireDatastore(vault) reads — strip it and
 * datastore_expand fails outright. It is not "a param the schema ignores"; it is the
 * subject of the call. (I removed it once on exactly that misreading. CI said no.)
 */
test.describe('Datastore Lifecycle @bridge', () => {
  let runner: BridgeTestRunner;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
    await runner.resetWorkerState();
  });

  test('datastore_expand should expand size', async () => {
    // Expand auto-mounts if needed (BTRFS online resize requires mounted state)
    const result = await runner.datastoreExpand('2G', DEFAULT_DATASTORE_PATH);
    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('datastore_resize should resize datastore', async () => {
    const result = await runner.datastoreResize('3G', DEFAULT_DATASTORE_PATH);
    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('datastore_validate should validate integrity', async () => {
    const result = await runner.datastoreValidate(DEFAULT_DATASTORE_PATH);
    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('datastore_status should report the base pool', async () => {
    const result = await runner.checkDatastore(DEFAULT_DATASTORE_PATH);
    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });
});

/**
 * Size parameters, against the verb that now OWNS creation.
 *
 * These used to drive `datastore_init` with G/M sizes; the subject (parsing a size
 * and materializing a datastore of it) survives on `datastore_create`, so the
 * assertions move rather than disappear.
 */
test.describe('Datastore Size Parameters @bridge', () => {
  let runner: BridgeTestRunner;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
    await runner.resetWorkerState();
  });

  for (const [label, size] of [
    ['GB size', '5G'],
    ['MB size', '500M'],
    ['larger GB size', '10G'],
  ] as const) {
    test(`datastore_create with ${label} should work`, async () => {
      const name = `ds-size-${size.toLowerCase()}`;
      const result = await runner.datastoreCreate({ name, backend: 'local', size });
      expect(runner.isSuccess(result)).toBe(true);
      await runner.datastoreDelete(name);
    });
  }
});

/**
 * Full named-datastore lifecycle — the direct successor of the old
 * init -> check -> mount -> validate -> expand -> unmount ladder.
 */
test.describe
  .serial('Datastore Full Lifecycle @bridge @lifecycle', () => {
    let runner: BridgeTestRunner;
    const name = 'ds-lifecycle';

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();
    });

    test.afterAll(async () => {
      // Best-effort: a failed leg must not strand the datastore for the next run.
      await runner.datastoreDetach(name).catch(() => undefined);
      await runner.datastoreDelete(name).catch(() => undefined);
    });

    test('1. datastore_create: create the datastore', async () => {
      const result = await runner.datastoreCreate({ name, backend: 'local', size: '1G' });
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('2. datastore_list: the registry reports it', async () => {
      const result = await runner.datastoreList();
      expect(runner.isSuccess(result)).toBe(true);
      // `datastore_list` shells out to `renet datastore list --json`, and the bridge
      // runs it with --debug, which interleaves renet's logs on stderr. Assert against
      // BOTH streams: the claim is "the registry reports it", not "on this fd".
      expect(`${result.stdout}${result.stderr}`).toContain(name);
    });

    test('3. datastore_attach: attach it', async () => {
      const result = await runner.datastoreAttach({ name });
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('4. datastore_validate: validate the pool', async () => {
      const result = await runner.datastoreValidate(DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('5. datastore_expand: expand the pool', async () => {
      const result = await runner.datastoreExpand('2G', DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('6. datastore_detach: detach it', async () => {
      const result = await runner.datastoreDetach(name);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('7. datastore_delete: remove it from the registry', async () => {
      const result = await runner.datastoreDelete(name);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });
