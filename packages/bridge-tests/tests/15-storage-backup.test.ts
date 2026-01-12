import { expect, test } from "@playwright/test";
import {
  DEFAULT_BRIDGE_IP,
  DEFAULT_DATASTORE_PATH,
  DEFAULT_RUSTFS_BUCKET,
  DEFAULT_WORKER_1_IP,
  DEFAULT_WORKER_2_IP,
  TEST_CONTAINER_PREFIX,
  TEST_REPOSITORY_NAME,
  TEST_TEAM,
  TEST_USER,
} from "../src/constants";
import { BridgeTestRunner } from "../src/utils/bridge/BridgeTestRunner";
import { DEFAULT_RUSTFS_CONFIG, StorageTestHelper } from "../src/utils/storage/StorageTestHelper";
import { VaultBuilder } from "../src/utils/vault/VaultBuilder";

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
 * - RustFS must be running on bridge VM (ops: ./go rustfs_start)
 * - rclone must be configured on worker VMs (ops: ./go rustfs_configure_workers)
 *
 * VMs are automatically started via global-setup.ts.
 */
test.describe("Storage Infrastructure @bridge @storage @infra", () => {
  let storage: StorageTestHelper;

  test.beforeAll(() => {
    storage = new StorageTestHelper(DEFAULT_BRIDGE_IP, DEFAULT_RUSTFS_CONFIG);
  });

  test("RustFS S3 endpoint should be accessible", async () => {
    const isAvailable = await storage.isAvailable();
    // Skip test if RustFS is not running (allows tests to run without storage)
    test.skip(!isAvailable, "RustFS S3 endpoint is not available");
    expect(isAvailable).toBe(true);
  });

  test("should be able to list buckets", async () => {
    const isAvailable = await storage.isAvailable();
    test.skip(!isAvailable, "RustFS S3 endpoint is not available");

    const buckets = await storage.listBuckets();
    expect(Array.isArray(buckets)).toBe(true);
  });

  test("should be able to create and delete test bucket", async () => {
    const isAvailable = await storage.isAvailable();
    test.skip(!isAvailable, "RustFS S3 endpoint is not available");

    const testBucket = await storage.createTestBucket("storage-test");
    expect(testBucket).toMatch(/^storage-test-\d+$/);

    // Cleanup
    await storage.cleanupTestBucket(testBucket);
  });

  test("should be able to upload and verify test file", async () => {
    const isAvailable = await storage.isAvailable();
    test.skip(!isAvailable, "RustFS S3 endpoint is not available");

    const testBucket = await storage.createTestBucket("upload-test");
    const testKey = `test-file-${Date.now()}.txt`;
    const testContent = "Hello from E2E storage test";

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

test.describe("Storage Backup Push @bridge @storage", () => {
  let runner: BridgeTestRunner;
  let storage: StorageTestHelper;

  test.beforeAll(() => {
    runner = BridgeTestRunner.forWorker();
    storage = new StorageTestHelper(DEFAULT_BRIDGE_IP, DEFAULT_RUSTFS_CONFIG);
  });

  test("push to S3 storage should generate valid command with rclone flags", async () => {
    const vault = VaultBuilder.forPush()
      .withTeam(TEST_TEAM)
      .withRepository("test-repo-guid", "storage-backup-repo")
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withStorage(storage.getVaultStorageConfig())
      .withPushParams({
        destinationType: "storage",
        dest: "backup.tar",
        storages: ["rustfs"],
      });

    const result = await runner.pushWithVault(vault);

    // Command is logged in stderr, combine both for verification
    const output = result.stdout + result.stderr;

    // Verify rclone flags are present in the command
    expect(output).toContain("--rclone-backend");
    expect(output).toContain("--rclone-bucket");
    expect(output).toContain("s3");
    expect(output).toContain(DEFAULT_RUSTFS_BUCKET); // bucket name
  });

  test("push to storage with multiple targets should work", async () => {
    const vault = VaultBuilder.forPush()
      .withTeam(TEST_TEAM)
      .withRepository("test-repo-guid", "multi-storage-repo")
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withStorages([
        {
          name: "storage1",
          type: "s3",
          bucket: "bucket1",
          accessKey: "key1",
          secretKey: "secret1",
        },
        {
          name: "storage2",
          type: "s3",
          bucket: "bucket2",
          accessKey: "key2",
          secretKey: "secret2",
        },
      ])
      .withPushParams({
        destinationType: "storage",
        storages: ["storage1", "storage2"],
      });

    const result = await runner.pushWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("push to storage with state=online should work", async () => {
    const vault = VaultBuilder.forPush()
      .withTeam(TEST_TEAM)
      .withRepository("test-repo-guid", "online-storage-repo")
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withStorage(storage.getVaultStorageConfig())
      .withPushParams({
        destinationType: "storage",
        state: "online",
        dest: "backup-online.tar",
      });

    const result = await runner.pushWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("push to storage with checkpoint should work", async () => {
    const vault = VaultBuilder.forPush()
      .withTeam(TEST_TEAM)
      .withRepository("test-repo-guid", "checkpoint-storage-repo")
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withStorage(storage.getVaultStorageConfig())
      .withPushParams({
        destinationType: "storage",
        checkpoint: true,
        dest: "backup-checkpoint.tar",
      });

    const result = await runner.pushWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("push to storage with override should work", async () => {
    const vault = VaultBuilder.forPush()
      .withTeam(TEST_TEAM)
      .withRepository("test-repo-guid", "override-storage-repo")
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withStorage(storage.getVaultStorageConfig())
      .withPushParams({
        destinationType: "storage",
        override: true,
        dest: "backup-override.tar",
      });

    const result = await runner.pushWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });
});

test.describe("Storage Backup Pull @bridge @storage", () => {
  let runner: BridgeTestRunner;
  let storage: StorageTestHelper;

  test.beforeAll(() => {
    runner = BridgeTestRunner.forWorker();
    storage = new StorageTestHelper(DEFAULT_BRIDGE_IP, DEFAULT_RUSTFS_CONFIG);
  });

  test("pull from S3 storage should generate valid command with rclone flags", async () => {
    const vault = VaultBuilder.forPull()
      .withTeam(TEST_TEAM)
      .withRepository("test-repo-guid", "storage-pull-repo")
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withStorage(storage.getVaultStorageConfig())
      .withPullParams({
        sourceType: "storage",
        from: "rustfs",
      });

    const result = await runner.pullWithVault(vault);

    // Command is logged in stderr, combine both for verification
    const output = result.stdout + result.stderr;

    // Verify rclone flags are present in the command
    expect(output).toContain("--rclone-backend");
    expect(output).toContain("--rclone-bucket");
    expect(output).toContain("s3");
    expect(output).toContain(DEFAULT_RUSTFS_BUCKET); // bucket name
  });

  test("pull from storage with grand should work", async () => {
    const vault = VaultBuilder.forPull()
      .withTeam(TEST_TEAM)
      .withRepository("test-repo-guid", "grand-pull-repo")
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withStorage(storage.getVaultStorageConfig())
      .withPullParams({
        sourceType: "storage",
        from: "rustfs",
        grand: "grand-repo-guid",
      });

    const result = await runner.pullWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });
});

test.describe("Mixed Backup Operations @bridge @storage", () => {
  let runner: BridgeTestRunner;
  let storage: StorageTestHelper;

  test.beforeAll(() => {
    runner = BridgeTestRunner.forWorker();
    storage = new StorageTestHelper(DEFAULT_BRIDGE_IP, DEFAULT_RUSTFS_CONFIG);
  });

  test("push to machine should still work alongside storage", async () => {
    const vault = VaultBuilder.forPush()
      .withTeam(TEST_TEAM)
      .withRepository("test-repo-guid", "machine-push-repo")
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withDestinationMachine(DEFAULT_WORKER_2_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withPushParams({
        destinationType: "machine",
        machines: [DEFAULT_WORKER_2_IP],
        tag: "v1.0.0",
      });

    const result = await runner.pushWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("pull from machine should still work", async () => {
    const vault = VaultBuilder.forPull()
      .withTeam(TEST_TEAM)
      .withRepository("test-repo-guid", "machine-pull-repo")
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withSourceMachine(DEFAULT_WORKER_2_IP, TEST_USER)
      .withPullParams({
        sourceType: "machine",
        from: DEFAULT_WORKER_2_IP,
      });

    const result = await runner.pullWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("push with combined options should work", async () => {
    const vault = VaultBuilder.forPush()
      .withTeam(TEST_TEAM)
      .withRepository("test-repo-guid", "combined-repo")
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withStorage(storage.getVaultStorageConfig())
      .withPushParams({
        destinationType: "storage",
        dest: "combined-backup.tar",
        state: "offline",
        checkpoint: true,
        override: true,
        grand: "grand-repo-guid",
      });

    const result = await runner.pushWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });
});

test.describe("Storage Types Support @bridge @storage", () => {
  let runner: BridgeTestRunner;

  test.beforeAll(() => {
    runner = BridgeTestRunner.forWorker();
  });

  test("S3 storage type should generate correct rclone backend", async () => {
    const vault = VaultBuilder.forPush()
      .withTeam(TEST_TEAM)
      .withRepository(TEST_REPOSITORY_NAME, TEST_REPOSITORY_NAME)
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withStorage({
        name: "s3-storage",
        type: "s3",
        endpoint: "http://localhost:9000",
        bucket: "test-bucket",
        accessKey: "key",
        secretKey: "secret",
      })
      .withPushParams({ destinationType: "storage", storages: ["s3-storage"] });

    const result = await runner.pushWithVault(vault);
    const output = result.stdout + result.stderr;
    expect(output).toContain("--rclone-backend s3");
    expect(output).toContain("--rclone-bucket test-bucket");
    expect(output).toContain("s3-endpoint=http://localhost:9000");
  });

  test("B2 storage type should generate correct rclone backend", async () => {
    const vault = VaultBuilder.forPush()
      .withTeam(TEST_TEAM)
      .withRepository(TEST_REPOSITORY_NAME, TEST_REPOSITORY_NAME)
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withStorage({
        name: "b2-storage",
        type: "b2",
        bucket: "test-bucket",
        accessKey: "key",
        secretKey: "secret",
      })
      .withPushParams({ destinationType: "storage", storages: ["b2-storage"] });

    const result = await runner.pushWithVault(vault);
    const output = result.stdout + result.stderr;
    expect(output).toContain("--rclone-backend b2");
    expect(output).toContain("--rclone-bucket test-bucket");
  });

  test("Azure storage type should generate correct rclone backend", async () => {
    const vault = VaultBuilder.forPush()
      .withTeam(TEST_TEAM)
      .withRepository(TEST_REPOSITORY_NAME, TEST_REPOSITORY_NAME)
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withStorage({
        name: "azure-storage",
        type: "azure",
        bucket: TEST_CONTAINER_PREFIX,
        accessKey: "account",
        secretKey: "key",
      })
      .withPushParams({ destinationType: "storage", storages: ["azure-storage"] });

    const result = await runner.pushWithVault(vault);
    const output = result.stdout + result.stderr;
    expect(output).toContain("--rclone-backend azure");
    expect(output).toContain(`--rclone-bucket ${TEST_CONTAINER_PREFIX}`);
  });

  test("GCS storage type should generate correct rclone backend", async () => {
    const vault = VaultBuilder.forPush()
      .withTeam(TEST_TEAM)
      .withRepository(TEST_REPOSITORY_NAME, TEST_REPOSITORY_NAME)
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withStorage({
        name: "gcs-storage",
        type: "gcs",
        bucket: "test-bucket",
        accessKey: "service-account",
        secretKey: "key-json",
      })
      .withPushParams({ destinationType: "storage", storages: ["gcs-storage"] });

    const result = await runner.pushWithVault(vault);
    const output = result.stdout + result.stderr;
    expect(output).toContain("--rclone-backend gcs");
    expect(output).toContain("--rclone-bucket test-bucket");
  });
});
