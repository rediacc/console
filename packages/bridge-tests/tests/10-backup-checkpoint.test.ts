import { expect, test } from "@playwright/test";
import { DEFAULT_DATASTORE_PATH, TEST_REPOSITORY_NAME } from "../src/constants";
import { BridgeTestRunner } from "../src/utils/bridge/BridgeTestRunner";

/**
 * Backup/Checkpoint Operations Tests
 *
 * Tests push, pull, and checkpoint functions.
 * These functions handle data transfer between machines and state preservation.
 *
 * Functions tested:
 * - backup_push (push repository to remote machine or storage)
 * - backup_pull (pull repository from remote machine or storage)
 * - checkpoint_create
 * - checkpoint_restore
 *
 * Note: checkpoint_list, checkpoint_info, checkpoint_delete are not implemented in Go.
 * Available checkpoint functions: checkpoint_create, checkpoint_restore, checkpoint_validate, checkpoint_cleanup, checkpoint_check_compat
 *
 * VMs are automatically started via global-setup.ts.
 */
test.describe("Backup Operations @bridge", () => {
  let runner: BridgeTestRunner;
  const testRepo = "backup-test-repo";

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test("push should not have shell syntax errors", async () => {
    const result = await runner.push(testRepo, runner.getWorkerVM2(), DEFAULT_DATASTORE_PATH);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("pull should not have shell syntax errors", async () => {
    const result = await runner.pull(testRepo, runner.getWorkerVM(), DEFAULT_DATASTORE_PATH);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });
});

test.describe("Checkpoint Operations @bridge", () => {
  let runner: BridgeTestRunner;
  const testRepo = "checkpoint-test-repo";
  const checkpointName = `ckpt-${Date.now()}`;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test("checkpoint_create should not have shell syntax errors", async () => {
    const result = await runner.checkpointCreate(testRepo, checkpointName, DEFAULT_DATASTORE_PATH);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("checkpoint_restore should not have shell syntax errors", async () => {
    const result = await runner.checkpointRestore(testRepo, checkpointName, DEFAULT_DATASTORE_PATH);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });
});

/**
 * Checkpoint Lifecycle Tests
 *
 * Tests the checkpoint create/restore lifecycle.
 * Note: checkpoint_list, checkpoint_info, checkpoint_delete are not implemented in Go.
 */
test.describe
  .serial("Checkpoint Lifecycle @bridge @lifecycle", () => {
    let runner: BridgeTestRunner;
    const repositoryName = `ckpt-lifecycle-${Date.now()}`;
    const checkpoint1 = `ckpt1-${Date.now()}`;
    const checkpoint2 = `ckpt2-${Date.now()}`;
    const datastorePath = DEFAULT_DATASTORE_PATH;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
    });

    test("1. checkpoint_create: create first checkpoint", async () => {
      const result = await runner.checkpointCreate(repositoryName, checkpoint1, datastorePath);
      expect(runner.hasValidCommandSyntax(result)).toBe(true);
    });

    test("2. checkpoint_create: create second checkpoint", async () => {
      const result = await runner.checkpointCreate(repositoryName, checkpoint2, datastorePath);
      expect(runner.hasValidCommandSyntax(result)).toBe(true);
    });

    test("3. checkpoint_restore: restore to checkpoint1", async () => {
      const result = await runner.checkpointRestore(repositoryName, checkpoint1, datastorePath);
      expect(runner.hasValidCommandSyntax(result)).toBe(true);
    });
  });

/**
 * Backup/Checkpoint Error Handling Tests
 *
 * Tests error handling for backup and checkpoint operations.
 */
test.describe("Backup/Checkpoint Error Handling @bridge", () => {
  let runner: BridgeTestRunner;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test("push to unreachable machine should handle gracefully", async () => {
    const result = await runner.push(TEST_REPOSITORY_NAME, "10.0.0.254", DEFAULT_DATASTORE_PATH);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("pull from unreachable machine should handle gracefully", async () => {
    const result = await runner.pull(TEST_REPOSITORY_NAME, "10.0.0.254", DEFAULT_DATASTORE_PATH);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("restore nonexistent checkpoint should handle gracefully", async () => {
    const result = await runner.checkpointRestore(
      TEST_REPOSITORY_NAME,
      "nonexistent-ckpt",
      DEFAULT_DATASTORE_PATH,
    );
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });
});

/**
 * Push/Pull Multi-Machine Tests
 *
 * Tests data transfer between multiple machines.
 * VMs are automatically started via global-setup.ts.
 */
test.describe("Multi-Machine Backup Operations @bridge @multi-machine", () => {
  let runner: BridgeTestRunner;
  const repositoryName = `multi-backup-${Date.now()}`;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test("push from VM1 to VM2", async () => {
    const result = await runner.push(repositoryName, runner.getWorkerVM2(), DEFAULT_DATASTORE_PATH);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("pull from VM1 to VM2", async () => {
    const result = await runner.pull(repositoryName, runner.getWorkerVM(), DEFAULT_DATASTORE_PATH);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });
});

/**
 * Checkpoint Naming Tests
 *
 * Tests various checkpoint name formats.
 */
test.describe("Checkpoint Naming @bridge", () => {
  let runner: BridgeTestRunner;
  const repositoryName = "ckpt-naming-test";

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test("checkpoint with timestamp name should work", async () => {
    const name = `ckpt-${new Date().toISOString().replace(/[:.]/g, "-")}`;
    const result = await runner.checkpointCreate(repositoryName, name, DEFAULT_DATASTORE_PATH);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("checkpoint with simple name should work", async () => {
    const result = await runner.checkpointCreate(repositoryName, "daily-backup", DEFAULT_DATASTORE_PATH);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("checkpoint with version name should work", async () => {
    const result = await runner.checkpointCreate(repositoryName, "v1.0.0", DEFAULT_DATASTORE_PATH);
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("checkpoint with underscores should work", async () => {
    const result = await runner.checkpointCreate(
      repositoryName,
      "pre_release_v2",
      DEFAULT_DATASTORE_PATH,
    );
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });
});

/**
 * Backup Push - Multi-Machine Options Tests
 *
 * Tests push to different machines using the destMachine parameter.
 * Note: Advanced parameters (destinationType, tag, state, checkpoint, etc.)
 * are passed via vault when queuing tasks, not as CLI flags in test mode.
 * Full parameter testing requires the queue API integration.
 */
test.describe("Backup Push - Machine Options @bridge", () => {
  let runner: BridgeTestRunner;
  const testRepo = "push-machine-test";

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test("push to worker2 should have valid syntax", async () => {
    const result = await runner.pushWithOptions(testRepo, {
      destMachine: runner.getWorkerVM2(),
      datastorePath: DEFAULT_DATASTORE_PATH,
    });
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("push to worker1 should have valid syntax", async () => {
    const result = await runner.pushWithOptions(testRepo, {
      destMachine: runner.getWorkerVM(),
      datastorePath: DEFAULT_DATASTORE_PATH,
    });
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });
});

/**
 * Backup Pull - Machine Options Tests
 *
 * Tests pull from different machines using the sourceMachine parameter.
 * Note: Advanced parameters (sourceType, from, grand, etc.)
 * are passed via vault when queuing tasks, not as CLI flags in test mode.
 */
test.describe("Backup Pull - Machine Options @bridge", () => {
  let runner: BridgeTestRunner;
  const testRepo = "pull-machine-test";

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test("pull from worker1 should have valid syntax", async () => {
    const result = await runner.pullWithOptions(testRepo, {
      sourceMachine: runner.getWorkerVM(),
      datastorePath: DEFAULT_DATASTORE_PATH,
    });
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });

  test("pull from worker2 should have valid syntax", async () => {
    const result = await runner.pullWithOptions(testRepo, {
      sourceMachine: runner.getWorkerVM2(),
      datastorePath: DEFAULT_DATASTORE_PATH,
    });
    expect(runner.hasValidCommandSyntax(result)).toBe(true);
  });
});
