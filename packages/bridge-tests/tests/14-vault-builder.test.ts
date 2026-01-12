import { expect, test } from "@playwright/test";
import {
  DEFAULT_DATASTORE_PATH,
  DEFAULT_RUSTFS_ACCESS_KEY,
  DEFAULT_RUSTFS_ENDPOINT,
  DEFAULT_RUSTFS_SECRET_KEY,
  DEFAULT_WORKER_1_IP,
  DEFAULT_WORKER_2_IP,
  TEST_REPOSITORY_NAME,
  TEST_TEAM,
  TEST_USER,
} from "../src/constants";
import { BridgeTestRunner } from "../src/utils/bridge/BridgeTestRunner";
import { VaultBuilder } from "../src/utils/vault/VaultBuilder";

/**
 * VaultBuilder Integration Tests
 *
 * Tests the VaultBuilder utility for constructing vault JSON for E2E testing.
 * These tests verify:
 * - VaultBuilder produces valid vault JSON structure
 * - Vaults can be loaded via renet --vault-file flag
 * - All backup_push/pull parameters are testable
 *
 * VMs are automatically started via global-setup.ts.
 */
test.describe("VaultBuilder Structure @bridge @vault", () => {
  test("should create valid vault JSON with minimal config", () => {
    const vault = new VaultBuilder()
      .withFunction("backup_push")
      .withTeam(TEST_TEAM)
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .build();

    expect(vault.$schema).toBe("queue-vault-v2");
    expect(vault.version).toBe("2.0");
    expect(vault.task.function).toBe("backup_push");
    expect(vault.task.team).toBe(TEST_TEAM);
    expect(vault.machine.ip).toBe(DEFAULT_WORKER_1_IP);
    expect(vault.machine.user).toBe(TEST_USER);
    expect(vault.machine.datastore).toBe(DEFAULT_DATASTORE_PATH);
  });

  test("should create vault with repository config", () => {
    const vault = new VaultBuilder()
      .withFunction("backup_push")
      .withTeam(TEST_TEAM)
      .withRepository("repo-guid-123", TEST_REPOSITORY_NAME, 2816)
      .build();

    expect(vault.task.repository).toBe(TEST_REPOSITORY_NAME);
    expect(vault.repositories).toBeDefined();
    expect(vault.repositories![TEST_REPOSITORY_NAME]).toEqual({
      guid: "repo-guid-123",
      name: TEST_REPOSITORY_NAME,
      network_id: 2816,
    });
    expect(vault.params?.repository).toBe("repo-guid-123");
    expect(vault.params?.repositoryName).toBe(TEST_REPOSITORY_NAME);
  });

  test("should create vault with push params", () => {
    const vault = new VaultBuilder()
      .withFunction("backup_push")
      .withPushParams({
        destinationType: "machine",
        to: "dest-machine",
        tag: "v1.0.0",
        state: "online",
        checkpoint: true,
        override: false,
      })
      .build();

    expect(vault.params?.destinationType).toBe("machine");
    expect(vault.params?.to).toBe("dest-machine");
    expect(vault.params?.tag).toBe("v1.0.0");
    expect(vault.params?.state).toBe("online");
    expect(vault.params?.checkpoint).toBe(true);
    expect(vault.params?.override).toBe(false);
  });

  test("should create vault with pull params", () => {
    const vault = new VaultBuilder()
      .withFunction("backup_pull")
      .withPullParams({
        sourceType: "storage",
        from: "rustfs-storage",
        grand: "grand-repo-guid",
      })
      .build();

    expect(vault.params?.sourceType).toBe("storage");
    expect(vault.params?.from).toBe("rustfs-storage");
    expect(vault.params?.grand).toBe("grand-repo-guid");
  });

  test("should create vault with storage systems", () => {
    const vault = new VaultBuilder()
      .withFunction("backup_push")
      .withStorage({
        name: "rustfs",
        type: "s3",
        endpoint: DEFAULT_RUSTFS_ENDPOINT,
        bucket: "test-bucket",
        accessKey: DEFAULT_RUSTFS_ACCESS_KEY,
        secretKey: DEFAULT_RUSTFS_SECRET_KEY,
        region: "us-east-1",
      })
      .build();

    expect(vault.storage_systems).toBeDefined();
    expect(vault.storage_systems!["rustfs"]).toEqual({
      backend: "s3",
      bucket: "test-bucket",
      region: "us-east-1",
      folder: undefined,
      parameters: {
        endpoint: DEFAULT_RUSTFS_ENDPOINT,
        access_key_id: DEFAULT_RUSTFS_ACCESS_KEY,
        secret_access_key: DEFAULT_RUSTFS_SECRET_KEY,
      },
    });
  });

  test("should create vault with multiple storages", () => {
    const vault = new VaultBuilder()
      .withFunction("backup_push")
      .withStorages([
        {
          name: "s3-storage",
          type: "s3",
          bucket: "bucket1",
          accessKey: "key1",
          secretKey: "secret1",
        },
        {
          name: "b2-storage",
          type: "b2",
          bucket: "bucket2",
          accessKey: "key2",
          secretKey: "secret2",
        },
      ])
      .withPushParams({ storages: ["s3-storage", "b2-storage"] })
      .build();

    const storageSystems = vault.storage_systems ?? {};
    expect(Object.keys(storageSystems)).toHaveLength(2);
    expect(vault.params?.storages).toBe("s3-storage,b2-storage");
  });

  test("should create vault with destination machine", () => {
    const vault = new VaultBuilder()
      .withFunction("backup_push")
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withDestinationMachine(DEFAULT_WORKER_2_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .build();

    expect(vault.extra_machines).toBeDefined();
    expect(vault.extra_machines!.destination).toEqual({
      ip: DEFAULT_WORKER_2_IP,
      user: TEST_USER,
      port: 22,
      datastore: DEFAULT_DATASTORE_PATH,
    });
    expect(vault.params?.dest_machine).toBe(DEFAULT_WORKER_2_IP);
  });

  test("should create vault with source machine", () => {
    const vault = new VaultBuilder()
      .withFunction("backup_pull")
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withSourceMachine(DEFAULT_WORKER_2_IP, TEST_USER)
      .build();

    expect(vault.extra_machines).toBeDefined();
    expect(vault.extra_machines!.source).toEqual({
      ip: DEFAULT_WORKER_2_IP,
      user: TEST_USER,
      port: 22,
    });
    expect(vault.params?.source_machine).toBe(DEFAULT_WORKER_2_IP);
  });

  test("should serialize to JSON", () => {
    const vault = new VaultBuilder().withFunction("backup_push").withTeam(TEST_TEAM);

    const json = vault.toJSON();
    expect(typeof json).toBe("string");
    expect(() => JSON.parse(json)).not.toThrow();

    const parsed = JSON.parse(json);
    expect(parsed.$schema).toBe("queue-vault-v2");
  });

  test("static forPush creates backup_push vault", () => {
    const vault = VaultBuilder.forPush().build();
    expect(vault.task.function).toBe("backup_push");
  });

  test("static forPull creates backup_pull vault", () => {
    const vault = VaultBuilder.forPull().build();
    expect(vault.task.function).toBe("backup_pull");
  });
});

test.describe("VaultBuilder with Renet @bridge @vault", () => {
  let runner: BridgeTestRunner;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test("push with vault should generate valid command", async () => {
    const vault = new VaultBuilder()
      .withFunction("backup_push")
      .withTeam(TEST_TEAM)
      .withRepository("test-repo-guid", TEST_REPOSITORY_NAME)
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withPushParams({
        destinationType: "machine",
        to: DEFAULT_WORKER_2_IP,
        tag: "v1.0.0",
      });

    const result = await runner.pushWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("pull with vault should generate valid command", async () => {
    const vault = new VaultBuilder()
      .withFunction("backup_pull")
      .withTeam(TEST_TEAM)
      .withRepository("test-repo-guid", TEST_REPOSITORY_NAME)
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withPullParams({
        sourceType: "machine",
        from: DEFAULT_WORKER_2_IP,
      });

    const result = await runner.pullWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("push with checkpoint flag should work", async () => {
    const vault = new VaultBuilder()
      .withFunction("backup_push")
      .withTeam(TEST_TEAM)
      .withRepository("test-repo-guid", TEST_REPOSITORY_NAME)
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withPushParams({
        destinationType: "machine",
        checkpoint: true,
      });

    const result = await runner.pushWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
    // Checkpoint flag should be processed without errors
  });

  test("push with storage destination should work", async () => {
    const vault = new VaultBuilder()
      .withFunction("backup_push")
      .withTeam(TEST_TEAM)
      .withRepository("test-repo-guid", TEST_REPOSITORY_NAME)
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withStorage({
        name: "rustfs",
        type: "s3",
        endpoint: DEFAULT_RUSTFS_ENDPOINT,
        bucket: "test-bucket",
        accessKey: DEFAULT_RUSTFS_ACCESS_KEY,
        secretKey: DEFAULT_RUSTFS_SECRET_KEY,
      })
      .withPushParams({
        destinationType: "storage",
        dest: "backup.tar",
        storages: ["rustfs"],
      });

    const result = await runner.pushWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("pull with grand param should work", async () => {
    const vault = new VaultBuilder()
      .withFunction("backup_pull")
      .withTeam(TEST_TEAM)
      .withRepository("test-repo-guid", TEST_REPOSITORY_NAME)
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withPullParams({
        sourceType: "machine",
        from: DEFAULT_WORKER_2_IP,
        grand: "grand-repo-guid",
      });

    const result = await runner.pullWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });
});

test.describe("VaultBuilder Push Destination Types @bridge @vault", () => {
  let runner: BridgeTestRunner;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test("push with destinationType=machine should work", async () => {
    const vault = VaultBuilder.forPush()
      .withTeam(TEST_TEAM)
      .withRepository(TEST_REPOSITORY_NAME, TEST_REPOSITORY_NAME)
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withDestinationMachine(DEFAULT_WORKER_2_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withPushParams({
        destinationType: "machine",
        machines: [DEFAULT_WORKER_2_IP],
      });

    const result = await runner.pushWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("push with destinationType=storage should work", async () => {
    const vault = VaultBuilder.forPush()
      .withTeam(TEST_TEAM)
      .withRepository(TEST_REPOSITORY_NAME, TEST_REPOSITORY_NAME)
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withStorage({
        name: "test-storage",
        type: "s3",
        bucket: "test-bucket",
        accessKey: "key",
        secretKey: "secret",
      })
      .withPushParams({
        destinationType: "storage",
        storages: ["test-storage"],
      });

    const result = await runner.pushWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });
});

test.describe("VaultBuilder Pull Source Types @bridge @vault", () => {
  let runner: BridgeTestRunner;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test("pull with sourceType=machine should work", async () => {
    const vault = VaultBuilder.forPull()
      .withTeam(TEST_TEAM)
      .withRepository(TEST_REPOSITORY_NAME, TEST_REPOSITORY_NAME)
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withSourceMachine(DEFAULT_WORKER_2_IP, TEST_USER)
      .withPullParams({
        sourceType: "machine",
        from: DEFAULT_WORKER_2_IP,
      });

    const result = await runner.pullWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("pull with sourceType=storage should work", async () => {
    const vault = VaultBuilder.forPull()
      .withTeam(TEST_TEAM)
      .withRepository(TEST_REPOSITORY_NAME, TEST_REPOSITORY_NAME)
      .withMachine(DEFAULT_WORKER_1_IP, TEST_USER, DEFAULT_DATASTORE_PATH)
      .withStorage({
        name: "test-storage",
        type: "s3",
        bucket: "test-bucket",
        accessKey: "key",
        secretKey: "secret",
      })
      .withPullParams({
        sourceType: "storage",
        from: "test-storage",
      });

    const result = await runner.pullWithVault(vault);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });
});
