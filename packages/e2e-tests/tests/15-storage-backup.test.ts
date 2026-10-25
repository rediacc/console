import { expect, test } from '@playwright/test';
import {
  DEFAULT_BRIDGE_IP,
  DEFAULT_DATASTORE_PATH,
  DEFAULT_WORKER_1_IP,
  DEFAULT_WORKER_2_IP,
  TEST_TEAM,
  TEST_USER,
} from '../src/constants';
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
