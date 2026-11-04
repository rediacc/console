import { randomBytes } from 'node:crypto';
import { expect, test } from '@playwright/test';
import {
  DEFAULT_BRIDGE_IP,
  DEFAULT_DATASTORE_PATH,
  DEFAULT_WORKER_1_IP,
  DEFAULT_WORKER_2_IP,
  TEST_TEAM,
  TEST_USER,
} from '../src/constants';
import { e2eRepoGuid } from '../src/utils/licence';
import { RenetFunctionsTestRunner } from '../src/utils/renet-functions/RenetFunctionsTestRunner';
import { DEFAULT_RUSTFS_CONFIG, StorageTestHelper } from '../src/utils/storage/StorageTestHelper';
import { VaultBuilder } from '../src/utils/vault/VaultBuilder';

/**
 * Storage Backup Operations Tests
 *
 * Tests the S3-compatible storage the bridge VM serves (RustFS) and the
 * machine-to-machine backup_push / backup_pull that remains after the storage
 * arm was retired.
 *
 * Prerequisites:
 * - RustFS must be running on bridge VM (renet ops rustfs start)
 *
 * VMs are automatically started via global-setup.ts.
 */
test.describe('Storage Infrastructure @bridge @storage @infra', () => {
  let storage: StorageTestHelper;

  test.beforeAll(() => {
    storage = new StorageTestHelper(DEFAULT_BRIDGE_IP, DEFAULT_RUSTFS_CONFIG);
  });

  test('RustFS S3 endpoint should be accessible', async () => {
    const isAvailable = await storage.isAvailable();
    // Skip test if RustFS is not running (allows tests to run without storage)
    test.skip(!isAvailable, 'RustFS S3 endpoint is not available');
    expect(isAvailable).toBe(true);
  });

  test('should be able to list buckets', async () => {
    const isAvailable = await storage.isAvailable();
    test.skip(!isAvailable, 'RustFS S3 endpoint is not available');

    const buckets = await storage.listBuckets();
    expect(Array.isArray(buckets)).toBe(true);
  });

  test('should be able to create and delete test bucket', async () => {
    const isAvailable = await storage.isAvailable();
    test.skip(!isAvailable, 'RustFS S3 endpoint is not available');

    const testBucket = await storage.createTestBucket('storage-test');
    expect(testBucket).toMatch(/^storage-test-\d+$/);

    // Cleanup
    await storage.cleanupTestBucket(testBucket);
  });

  test('should be able to upload and verify test file', async () => {
    const isAvailable = await storage.isAvailable();
    test.skip(!isAvailable, 'RustFS S3 endpoint is not available');

    const testBucket = await storage.createTestBucket('upload-test');
    const testKey = `test-file-${Date.now()}.txt`;
    const testContent = 'Hello from E2E storage test';

    try {
      const uploadResult = await storage.uploadContent(testBucket, testKey, testContent);
      expect(uploadResult.success).toBe(true);

      const exists = await storage.objectExists(testBucket, testKey);
      expect(exists).toBe(true);

      const content = await storage.downloadContent(testBucket, testKey);
      expect(content?.trim()).toBe(testContent);
    } finally {
      await storage.cleanupTestBucket(testBucket);
    }
  });
});

/**
 * The storage arm of backup_push / backup_pull is retired: renet refuses a storage destination, and
 * its own unit tests pin that refusal. What ships is machine-to-machine transfer, so that is what
 * these assert.
 */
test.describe('Machine Backup Operations @bridge @storage', () => {
  let runner: RenetFunctionsTestRunner;

  test.beforeAll(() => {
    runner = RenetFunctionsTestRunner.forWorker();
  });

  test('push to machine should work', async () => {
    const vault = VaultBuilder.forPush()
      .withTeam(TEST_TEAM)
      .withRepository('test-repo-guid', 'machine-push-repo')
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withDestinationMachine(DEFAULT_WORKER_2_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withPushParams({
        destinationType: 'machine',
        machines: [DEFAULT_WORKER_2_IP],
        tag: 'v1.0.0',
      });

    const result = await runner.pushWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test('pull from machine should work', async () => {
    const vault = VaultBuilder.forPull()
      .withTeam(TEST_TEAM)
      .withRepository('test-repo-guid', 'machine-pull-repo')
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withSourceMachine(DEFAULT_WORKER_2_IP, TEST_USER)
      .withPullParams({
        sourceType: 'machine',
        from: DEFAULT_WORKER_2_IP,
      });

    const result = await runner.pullWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test('push to machine with combined options should work', async () => {
    const vault = VaultBuilder.forPush()
      .withTeam(TEST_TEAM)
      .withRepository('test-repo-guid', 'combined-repo')
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withDestinationMachine(DEFAULT_WORKER_2_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withPushParams({
        destinationType: 'machine',
        machines: [DEFAULT_WORKER_2_IP],
        state: 'offline',
        checkpoint: true,
        override: true,
        grand: 'grand-repo-guid',
      });

    const result = await runner.pushWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });
});

/**
 * The push bandwidth cap on a real transfer (PLAN-jobs-backup-real-machine-tests E4). renet's unit tests pin the argv (`rsync --bwlimit`); only a timed push shows the cap holds on the wire. 64 MiB of incompressible data at 2 MB/s needs about 33 s, so a push under 25 s means the cap was dropped. The unlimited push of the same image is the control: without it a slow fleet would pass the test on its own speed.
 */
test.describe
  .serial('Push bandwidth cap on a real transfer @bridge @storage', () => {
    test.setTimeout(900_000);
    const FILL_MIB = 64;
    const CAP_FLOOR_S = 25;
    const guid = e2eRepoGuid();
    const password = randomBytes(16).toString('hex');
    let runner: RenetFunctionsTestRunner;
    let controlSeconds = 0;

    // A distinct destination per push keeps the second push a full transfer, never an incremental one.
    const cappedDest = e2eRepoGuid();

    const timedPush = async (
      extra: string,
      dest = guid
    ): Promise<{ seconds: number; code: number; out: string }> => {
      const started = Date.now();
      const result = await runner.executeViaBridge(
        `sudo renet backup push --name "${guid}" --datastore "${DEFAULT_DATASTORE_PATH}"` +
          ` --target machine --dest-host "${DEFAULT_WORKER_2_IP}" --dest-path "${DEFAULT_DATASTORE_PATH}"` +
          ` --dest "${dest}" --force${extra}`,
        600_000
      );
      return {
        seconds: (Date.now() - started) / 1000,
        code: result.code,
        out: runner.getCombinedOutput(result).slice(-800),
      };
    };

    test.beforeAll(async () => {
      runner = RenetFunctionsTestRunner.forWorker();
      await runner.ensureDatastoreReady(DEFAULT_DATASTORE_PATH);
      const created = await runner.repositoryNew(guid, '256M', password, DEFAULT_DATASTORE_PATH);
      expect(
        created.code,
        `repository_create: ${runner.getCombinedOutput(created).slice(-600)}`
      ).toBe(0);
      const mounted = await runner.repositoryMount(guid, password, DEFAULT_DATASTORE_PATH);
      expect(
        mounted.code,
        `repository_mount: ${runner.getCombinedOutput(mounted).slice(-600)}`
      ).toBe(0);
      const fill = await runner.executeViaBridge(
        `sudo dd if=/dev/urandom of="${DEFAULT_DATASTORE_PATH}/mounts/${guid}/fill.bin" bs=1M count=${FILL_MIB} conv=fsync status=none`
      );
      expect(fill.code, `fill: ${runner.getCombinedOutput(fill)}`).toBe(0);
      const unmounted = await runner.repositoryUnmount(guid, DEFAULT_DATASTORE_PATH);
      expect(
        unmounted.code,
        `repository_unmount: ${runner.getCombinedOutput(unmounted).slice(-600)}`
      ).toBe(0);
    });

    test.afterAll(async () => {
      await runner.repositoryRm(guid, DEFAULT_DATASTORE_PATH).catch(() => undefined);
      await RenetFunctionsTestRunner.forWorker(2)
        .repositoryRm(guid, DEFAULT_DATASTORE_PATH)
        .catch(() => undefined);
      await RenetFunctionsTestRunner.forWorker(2)
        .repositoryRm(cappedDest, DEFAULT_DATASTORE_PATH)
        .catch(() => undefined);
    });

    test('control: the unlimited push finishes, and is timed', async () => {
      const r = await timedPush('');
      expect(r.code, `unlimited push: ${r.out}`).toBe(0);
      controlSeconds = r.seconds;
    });

    test('--bwlimit 2M stretches the same push to at least 25 s, and past the control', async () => {
      const r = await timedPush(' --bwlimit 2M', cappedDest);
      expect(r.code, `capped push: ${r.out}`).toBe(0);
      expect(r.seconds, `capped push took ${r.seconds}s`).toBeGreaterThanOrEqual(CAP_FLOOR_S);
      expect(r.seconds, `capped ${r.seconds}s vs control ${controlSeconds}s`).toBeGreaterThan(
        controlSeconds
      );
    });
  });
