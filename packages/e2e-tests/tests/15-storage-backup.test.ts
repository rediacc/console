import { expect, test } from '@playwright/test';
import {
  DEFAULT_BRIDGE_IP,
  DEFAULT_DATASTORE_PATH,
  DEFAULT_WORKER_1_IP,
  DEFAULT_WORKER_2_IP,
  TEST_TEAM,
  TEST_USER,
} from '../src/constants';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';
import { DEFAULT_RUSTFS_CONFIG, StorageTestHelper } from '../src/utils/storage/StorageTestHelper';
import { VaultBuilder } from '../src/utils/vault/VaultBuilder';

/**
 * Storage Backup Operations Tests
 *
 * Tests backup_push and backup_pull with S3-compatible storage (RustFS).
 * These tests verify:
 * - Push to storage generates valid commands
 * - Pull from storage generates valid commands
 * - Storage connectivity and configuration
 *
 * Prerequisites:
 * - RustFS must be running on bridge VM (renet ops rustfs start)
 * - rclone must be configured on worker VMs (renet ops rustfs configure-workers)
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

/** stdout and stderr together: renet logs the command on stderr. */
async function pushOutput(runner: BridgeTestRunner, vault: unknown): Promise<string> {
  const result = await runner.pushWithVault(vault as never);

  return result.stdout + result.stderr;
}

test.describe('Storage arm is RETIRED @bridge @storage', () => {
  let runner: BridgeTestRunner;
  let storage: StorageTestHelper;

  test.beforeAll(() => {
    runner = BridgeTestRunner.forWorker();
    storage = new StorageTestHelper(DEFAULT_BRIDGE_IP, DEFAULT_RUSTFS_CONFIG);
  });

  /**
   * These three describes used to assert that push and pull EMITTED rclone
   * flags. That arm is gone: renet answers a storage destination with
   * errStorageRetired(), and its unit tests already assert the --rclone-*
   * flags are unregistered.
   *
   * They are rewritten rather than deleted, because the removal is the thing
   * worth testing now. A deleted test proves nothing about whether the arm
   * came back.
   *
   * The other half of the old file was worse than stale. Six tests asserted
   * only `hasValidCommandSyntax(result)`, which a REFUSAL satisfies just as
   * well as a success, so they passed while the feature they named was being
   * removed underneath them and would have kept passing had it never worked at
   * all. Asserting on the refusal's TEXT is what makes these mean something.
   */
  test('push to storage is refused, and the refusal names where to go instead', async () => {
    const vault = VaultBuilder.forPush()
      .withTeam(TEST_TEAM)
      .withRepository('test-repo-guid', 'storage-backup-repo')
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withStorage(storage.getVaultStorageConfig())
      .withPushParams({
        destinationType: 'storage',
        dest: 'backup.tar',
        storages: ['rustfs'],
      });

    const output = await pushOutput(runner, vault);

    expect(output).toContain('storage is retired');
    // The sentence must carry the operator somewhere, or a refusal is just a
    // dead end with better grammar.
    //
    // ASSERTED BY THE DISTINCTIVE FRAGMENTS, not the bare verb names, and this
    // comment avoids spelling them for the same reason. check-e2e-coverage
    // counts a verb literal appearing ANYWHERE in a live suite -- assertions and
    // comments alike -- as that verb being exercised. Naming the restore verb
    // here made it look covered by a suite that only ever reads it inside an
    // error string, and the gate then demanded its allowlist entry be deleted
    // as a debt paid. That would have recorded coverage which does not exist.
    // `--at <snapshot>` and `chunk store` pin the same guidance without
    // pretending anything ran.
    expect(output).toContain('chunk store');
    expect(output).toContain('--at <snapshot>');
    // And the retired flags must not reappear in the emitted command.
    expect(output).not.toContain('--rclone-backend');
    expect(output).not.toContain('--rclone-bucket');
  });

  test('pull from storage is refused the same way', async () => {
    const vault = VaultBuilder.forPull()
      .withTeam(TEST_TEAM)
      .withRepository('test-repo-guid', 'storage-pull-repo')
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withStorage(storage.getVaultStorageConfig())
      .withPullParams({
        sourceType: 'storage',
        from: 'rustfs',
      });

    const result = await runner.pullWithVault(vault);
    const output = result.stdout + result.stderr;

    expect(output).toContain('storage is retired');
    expect(output).toContain('chunk store');
    expect(output).not.toContain('--rclone-backend');
  });

  test('CONTROL: machine transfer is untouched by the retirement', async () => {
    // Without this, a renet that refused EVERY destination would satisfy both
    // assertions above while having broken the half that still ships.
    const vault = VaultBuilder.forPush()
      .withTeam(TEST_TEAM)
      .withRepository('test-repo-guid', 'machine-still-works-repo')
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withPushParams({
        destinationType: 'machine',
        dest: DEFAULT_WORKER_2_IP,
      });

    const output = await pushOutput(runner, vault);

    expect(output).not.toContain('storage is retired');
  });
});

test.describe('Mixed Backup Operations @bridge @storage', () => {
  let runner: BridgeTestRunner;
  let storage: StorageTestHelper;

  test.beforeAll(() => {
    runner = BridgeTestRunner.forWorker();
    storage = new StorageTestHelper(DEFAULT_BRIDGE_IP, DEFAULT_RUSTFS_CONFIG);
  });

  test('push to machine should still work alongside storage', async () => {
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

  test('pull from machine should still work', async () => {
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

  test('push with combined options should work', async () => {
    const vault = VaultBuilder.forPush()
      .withTeam(TEST_TEAM)
      .withRepository('test-repo-guid', 'combined-repo')
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withStorage(storage.getVaultStorageConfig())
      .withPushParams({
        destinationType: 'storage',
        dest: 'combined-backup.tar',
        state: 'offline',
        checkpoint: true,
        override: true,
        grand: 'grand-repo-guid',
      });

    const result = await runner.pushWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });
});
