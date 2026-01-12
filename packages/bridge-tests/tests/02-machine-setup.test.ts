import { expect, test } from "@playwright/test";
import { DEFAULT_DATASTORE_PATH, DEFAULT_UID } from "../src/constants";
import { BridgeTestRunner } from "../src/utils/bridge/BridgeTestRunner";

/**
 * Machine Setup Tests
 *
 * All functions registered in GoExecutor (setup domain):
 * - setup, machine_fix_groups, machine_check_setup
 */
test.describe("Machine Setup Functions @bridge @smoke", () => {
  let runner: BridgeTestRunner;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test("setup should succeed", async () => {
    const result = await runner.setup(DEFAULT_DATASTORE_PATH, DEFAULT_UID);

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test("setup with custom datastore path should succeed", async () => {
    const result = await runner.setup("/custom/datastore/path", DEFAULT_UID);

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test("setup without explicit datastore path should use default", async () => {
    const result = await runner.testFunction({ function: "setup", uid: DEFAULT_UID });

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test("os_setup (alias) should work the same as setup", async () => {
    const result = await runner.osSetup(DEFAULT_DATASTORE_PATH, DEFAULT_UID);

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test("fix_user_groups should succeed", async () => {
    const result = await runner.fixUserGroups(DEFAULT_UID);

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });
});

/**
 * Setup Command Edge Cases
 */
test.describe("Setup Command Edge Cases @bridge", () => {
  let runner: BridgeTestRunner;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test("setup command should handle compound shell commands", async () => {
    const result = await runner.setup(DEFAULT_DATASTORE_PATH, DEFAULT_UID);

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.stderr).not.toMatch(/bash:.*syntax/i);
    expect(result.stderr).not.toMatch(/bash:.*unexpected/i);
  });

  test("setup with special characters in path should be handled", async () => {
    const result = await runner.setup("/mnt/data store", DEFAULT_UID);

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });
});

/**
 * Multi-Machine Setup Tests
 */
test.describe("Multi-Machine Setup @bridge @multi-machine", () => {
  let runner: BridgeTestRunner;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test("machine_check_setup on worker VM 1", async () => {
    const result = await runner.executeOnWorker(
      "renet bridge once --test-mode --function machine_check_setup",
    );

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test("machine_check_setup on worker VM 2", async () => {
    const result = await runner.executeOnWorker2(
      "renet bridge once --test-mode --function machine_check_setup",
    );

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test("parallel machine_check_setup on all workers", async () => {
    const results = await runner.executeOnAllWorkers(
      "renet bridge once --test-mode --function machine_check_setup",
    );

    for (const [_vm, result] of results) {
      expect(runner.isSuccess(result)).toBe(true);
      expect(result.code).toBe(0);
    }
  });
});
