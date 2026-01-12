import { expect, test } from "@playwright/test";
import { DEFAULT_DATASTORE_PATH, DEFAULT_NETWORK_ID, TEST_REPOSITORY_NAME } from "../src/constants";
import { BridgeTestRunner } from "../src/utils/bridge/BridgeTestRunner";

/**
 * Daemon Operations Tests (5 functions)
 *
 * Tests daemon management functions for repository services.
 *
 * Functions tested:
 * - daemon_start (system-level and repository-level)
 * - daemon_stop (system-level and repository-level)
 * - daemon_status (system-level and repository-level)
 * - daemon_restart
 * - daemon_logs
 *
 * Daemons are background services that run within a repository context.
 */
test.describe("Daemon Operations @bridge", () => {
  let runner: BridgeTestRunner;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
    await runner.resetWorkerState();
    // Setup daemon before all tests (required for start/stop/restart operations)
    const result = await runner.daemonSetup(DEFAULT_NETWORK_ID);
    if (!runner.isSuccess(result)) {
      throw new Error(`daemon_setup failed: ${runner.getCombinedOutput(result)}`);
    }
  });

  test.afterAll(async () => {
    // Teardown daemon after all tests
    await runner.daemonTeardown(DEFAULT_NETWORK_ID);
  });

  // ===========================================================================
  // Repository Daemon Functions
  // ===========================================================================

  test("daemon_start should not have shell syntax errors", async () => {
    const result = await runner.daemonStart(
      TEST_REPOSITORY_NAME,
      DEFAULT_DATASTORE_PATH,
      DEFAULT_NETWORK_ID,
    );
    expect(runner.isSuccess(result)).toBe(true);
  });

  test("daemon_stop should not have shell syntax errors", async () => {
    const result = await runner.daemonStop(
      TEST_REPOSITORY_NAME,
      DEFAULT_DATASTORE_PATH,
      DEFAULT_NETWORK_ID,
    );
    expect(runner.isSuccess(result)).toBe(true);
  });

  test("daemon_status should not have shell syntax errors", async () => {
    const result = await runner.daemonStatus(
      TEST_REPOSITORY_NAME,
      DEFAULT_DATASTORE_PATH,
      DEFAULT_NETWORK_ID,
    );
    expect(runner.isSuccess(result)).toBe(true);
  });

  test("daemon_restart should not have shell syntax errors", async () => {
    const result = await runner.daemonRestart(
      TEST_REPOSITORY_NAME,
      DEFAULT_DATASTORE_PATH,
      DEFAULT_NETWORK_ID,
    );
    expect(runner.isSuccess(result)).toBe(true);
  });

  test("daemon_logs should not have shell syntax errors", async () => {
    const result = await runner.daemonLogs(
      TEST_REPOSITORY_NAME,
      DEFAULT_DATASTORE_PATH,
      DEFAULT_NETWORK_ID,
    );
    expect(runner.isSuccess(result)).toBe(true);
  });

  // ===========================================================================
  // System-level Daemon Functions (no repository context)
  // ===========================================================================

  test("daemon_start (system) should not have shell syntax errors", async () => {
    const result = await runner.renetStart(DEFAULT_NETWORK_ID);
    expect(runner.isSuccess(result)).toBe(true);
  });

  test("daemon_stop (system) should not have shell syntax errors", async () => {
    const result = await runner.renetStop(DEFAULT_NETWORK_ID);
    expect(runner.isSuccess(result)).toBe(true);
  });

  test("daemon_status (system) should not have shell syntax errors", async () => {
    const result = await runner.renetStatus(DEFAULT_NETWORK_ID);
    expect(runner.isSuccess(result)).toBe(true);
  });
});

/**
 * Daemon Lifecycle Tests
 *
 * Tests daemon start/stop lifecycle in order.
 */
test.describe
  .serial("Daemon Lifecycle @bridge @lifecycle", () => {
    let runner: BridgeTestRunner;
    const repositoryName = `daemon-lifecycle-${Date.now()}`;
    const datastorePath = DEFAULT_DATASTORE_PATH;
    const networkId = DEFAULT_NETWORK_ID;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();
    });

    test("1. daemon_status: check initial status", async () => {
      const result = await runner.daemonStatus(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("2. daemon_setup: set up daemon service", async () => {
      const result = await runner.daemonSetup(networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("3. daemon_start: start daemon", async () => {
      const result = await runner.daemonStart(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("4. daemon_status: verify daemon started", async () => {
      const result = await runner.daemonStatus(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("5. daemon_logs: check daemon logs", async () => {
      const result = await runner.daemonLogs(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("6. daemon_restart: restart daemon", async () => {
      const result = await runner.daemonRestart(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("7. daemon_stop: stop daemon", async () => {
      const result = await runner.daemonStop(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("8. daemon_status: verify daemon stopped", async () => {
      const result = await runner.daemonStatus(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("9. daemon_teardown: tear down daemon service", async () => {
      const result = await runner.daemonTeardown(networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * System Daemon Lifecycle Tests
 *
 * Tests system-level daemon service lifecycle.
 */
test.describe
  .serial("System Daemon Lifecycle @bridge @lifecycle", () => {
    let runner: BridgeTestRunner;
    const networkId = DEFAULT_NETWORK_ID;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();
    });

    test("1. daemon_status: check initial status", async () => {
      const result = await runner.renetStatus(networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("2. daemon_setup: set up daemon service", async () => {
      const result = await runner.daemonSetup(networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("3. daemon_start: start daemon service", async () => {
      const result = await runner.renetStart(networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("4. daemon_status: verify daemon started", async () => {
      const result = await runner.renetStatus(networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("5. daemon_stop: stop daemon service", async () => {
      const result = await runner.renetStop(networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("6. daemon_status: verify daemon stopped", async () => {
      const result = await runner.renetStatus(networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("7. daemon_teardown: tear down daemon service", async () => {
      const result = await runner.daemonTeardown(networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Daemon Error Handling Tests
 *
 * Tests error handling for daemon operations.
 */
test.describe("Daemon Error Handling @bridge", () => {
  let runner: BridgeTestRunner;
  const networkId = DEFAULT_NETWORK_ID;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
    await runner.resetWorkerState();
    // Setup daemon before all error handling tests
    const result = await runner.daemonSetup(networkId);
    if (!runner.isSuccess(result)) {
      throw new Error(`daemon_setup failed: ${runner.getCombinedOutput(result)}`);
    }
  });

  test.afterAll(async () => {
    // Teardown daemon after all tests
    await runner.daemonTeardown(networkId);
  });

  test("daemon operations on nonexistent repository should handle gracefully", async () => {
    const nonexistent = "nonexistent-daemon-xyz";

    const startResult = await runner.daemonStart(nonexistent, DEFAULT_DATASTORE_PATH, networkId);
    expect(runner.isSuccess(startResult)).toBe(true);

    const statusResult = await runner.daemonStatus(nonexistent, DEFAULT_DATASTORE_PATH, networkId);
    expect(runner.isSuccess(statusResult)).toBe(true);

    const stopResult = await runner.daemonStop(nonexistent, DEFAULT_DATASTORE_PATH, networkId);
    expect(runner.isSuccess(stopResult)).toBe(true);
  });

  test("daemon_stop when not running should handle gracefully", async () => {
    const result = await runner.daemonStop("not-running", DEFAULT_DATASTORE_PATH, networkId);
    expect(runner.isSuccess(result)).toBe(true);
  });

  test("daemon_restart when not running should handle gracefully", async () => {
    const result = await runner.daemonRestart("not-running", DEFAULT_DATASTORE_PATH, networkId);
    expect(runner.isSuccess(result)).toBe(true);
  });

  test("daemon_logs when no logs exist should handle gracefully", async () => {
    const result = await runner.daemonLogs("no-logs", DEFAULT_DATASTORE_PATH, networkId);
    expect(runner.isSuccess(result)).toBe(true);
  });
});

/**
 * Multiple Daemon Cycles Tests
 *
 * Tests multiple start/stop cycles.
 */
test.describe("Daemon Multiple Cycles @bridge", () => {
  let runner: BridgeTestRunner;
  const repositoryName = `multi-daemon-${Date.now()}`;
  const networkId = DEFAULT_NETWORK_ID;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
    await runner.resetWorkerState();
    // Setup daemon before all cycle tests
    const result = await runner.daemonSetup(networkId);
    if (!runner.isSuccess(result)) {
      throw new Error(`daemon_setup failed: ${runner.getCombinedOutput(result)}`);
    }
  });

  test.afterAll(async () => {
    // Teardown daemon after all tests
    await runner.daemonTeardown(networkId);
  });

  test("multiple daemon start/stop cycles should work", async () => {
    const datastorePath = DEFAULT_DATASTORE_PATH;

    for (let i = 0; i < 3; i++) {
      const startResult = await runner.daemonStart(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(startResult)).toBe(true);

      const stopResult = await runner.daemonStop(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(stopResult)).toBe(true);
    }
  });

  test("multiple restart cycles should work", async () => {
    const datastorePath = DEFAULT_DATASTORE_PATH;

    for (let i = 0; i < 3; i++) {
      const result = await runner.daemonRestart(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    }
  });
});
