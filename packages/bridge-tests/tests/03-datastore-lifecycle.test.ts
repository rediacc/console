import { expect, test } from '@playwright/test';
import { DEFAULT_DATASTORE_PATH } from '../src/constants';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

/**
 * Datastore Lifecycle Tests
 *
 * Tests datastore operations via bridge once --test-mode.
 * Datastore functions are registered in executor_bridge.go.
 */
test.describe('Datastore Lifecycle @bridge', () => {
  let runner: BridgeTestRunner;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
    await runner.resetWorkerState();
  });

  test('datastore_init should create datastore', async () => {
    const result = await runner.datastoreInit('1G', DEFAULT_DATASTORE_PATH, true);
    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('datastore_mount should mount datastore', async () => {
    const result = await runner.datastoreMount(DEFAULT_DATASTORE_PATH);
    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('datastore_unmount should unmount datastore', async () => {
    const result = await runner.datastoreUnmount(DEFAULT_DATASTORE_PATH);
    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('datastore_expand should expand size', async () => {
    // Expand auto-mounts if needed (BTRFS online resize requires mounted state)
    const result = await runner.datastoreExpand('2G', DEFAULT_DATASTORE_PATH);
    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('datastore_resize should resize datastore', async () => {
    // Resize requires unmounted state - unmount first
    await runner.datastoreUnmount(DEFAULT_DATASTORE_PATH);
    const result = await runner.datastoreResize('3G', DEFAULT_DATASTORE_PATH);
    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('datastore_validate should validate integrity', async () => {
    // Mount first for validation (after resize left it unmounted)
    await runner.datastoreMount(DEFAULT_DATASTORE_PATH);
    const result = await runner.datastoreValidate(DEFAULT_DATASTORE_PATH);
    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('check_datastore should verify datastore', async () => {
    const result = await runner.checkDatastore(DEFAULT_DATASTORE_PATH);
    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });
});

/**
 * Datastore Size Parameter Tests
 */
test.describe('Datastore Size Parameters @bridge', () => {
  let runner: BridgeTestRunner;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
    await runner.resetWorkerState();
  });

  test('datastore_init with GB size should work', async () => {
    const result = await runner.datastoreInit('5G', DEFAULT_DATASTORE_PATH, true);
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('datastore_init with MB size should work', async () => {
    const result = await runner.datastoreInit('500M', DEFAULT_DATASTORE_PATH, true);
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('datastore_init with larger GB size should work', async () => {
    const result = await runner.datastoreInit('10G', DEFAULT_DATASTORE_PATH, true);
    expect(runner.isSuccess(result)).toBe(true);
  });
});

/**
 * Datastore Full Lifecycle Test
 */
test.describe
  .serial('Datastore Full Lifecycle @bridge @lifecycle', () => {
    let runner: BridgeTestRunner;
    const datastorePath = '/mnt/test-datastore';

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();
      await runner.resetWorkerState(datastorePath);
    });

    test('1. datastore_init: create datastore', async () => {
      // Use force=true since resetWorkerState may leave the directory intact
      const result = await runner.datastoreInit('1G', datastorePath, true);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('2. check_datastore: verify datastore created', async () => {
      const result = await runner.checkDatastore(datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('3. datastore_mount: mount datastore', async () => {
      const result = await runner.datastoreMount(datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('4. datastore_validate: validate mounted datastore', async () => {
      const result = await runner.datastoreValidate(datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('5. datastore_expand: expand datastore size', async () => {
      const result = await runner.datastoreExpand('2G', datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('6. datastore_unmount: unmount datastore', async () => {
      const result = await runner.datastoreUnmount(datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });
