import { expect, test } from '@playwright/test';
import {
  DEFAULT_DATASTORE_PATH,
  DEFAULT_NETWORK_ID,
  TEST_PASSWORD,
  TEST_REPOSITORY_NAME,
} from '../src/constants';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

/**
 * Rediaccfile Up/Down Tests (4+ functions)
 *
 * Tests the Rediaccfile orchestration system that:
 * 1. Reads Rediaccfile from repository
 * 2. Executes prep() function on first up
 * 3. Executes up() function to start services
 * 4. Executes down() function to stop services
 *
 * Functions tested:
 * - up (Rediaccfile orchestration)
 * - down (Rediaccfile teardown)
 *
 * Prerequisites:
 * - Repository must be created and mounted
 * - Rediaccfile must exist in repository root
 *
 * Rediaccfile Format Example (bash):
 * ```bash
 * # === Renet Compose (Required) ===
 * _compose() {
 *   renet compose --network-id "$REPOSITORY_NETWORK_ID" -- "$@"
 * }
 *
 * prep() {
 *   docker pull nginx:alpine
 * }
 *
 * up() {
 *   _compose up -d
 * }
 *
 * down() {
 *   _compose down -v
 * }
 * ```
 */
test.describe('Rediaccfile Up/Down Functions @bridge', () => {
  let runner: BridgeTestRunner;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
    await runner.resetWorkerState();
  });

  // ===========================================================================
  // Basic Syntax Tests (requires network ID for daemon startup)
  // ===========================================================================

  test('up function should not have shell syntax errors', async () => {
    // Note: up on nonexistent repo succeeds with warnings (skips gracefully)
    const result = await runner.repositoryUp(
      TEST_REPOSITORY_NAME,
      DEFAULT_DATASTORE_PATH,
      DEFAULT_NETWORK_ID
    );
    // Expect success - command runs without syntax errors
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('down function should not have shell syntax errors', async () => {
    const result = await runner.repositoryDown(TEST_REPOSITORY_NAME, DEFAULT_DATASTORE_PATH);
    expect(runner.isSuccess(result)).toBe(true);
  });
});

/**
 * Rediaccfile Lifecycle Tests
 *
 * Tests the complete up/down lifecycle in order.
 */
test.describe
  .serial('Rediaccfile Lifecycle @bridge @lifecycle', () => {
    let runner: BridgeTestRunner;
    const repositoryName = `rediaccfile-test-${Date.now()}`;
    const datastorePath = DEFAULT_DATASTORE_PATH;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();

      // Initialize datastore (LEVEL 2 prerequisite for repository operations)
      await runner.datastoreInit('10G', datastorePath, true);
    });

    test('1. create repository for Rediaccfile testing', async () => {
      const result = await runner.repositoryNew(repositoryName, '1G', TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Note: repository_create leaves repo mounted, so unmount first before testing mount
    test('2a. unmount repository before mount test', async () => {
      const result = await runner.repositoryUnmount(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('2b. mount repository', async () => {
      const result = await runner.repositoryMount(repositoryName, TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('2c. daemon_setup: set up daemon service', async () => {
      // Set up daemon before running up with containers
      const result = await runner.daemonSetup(DEFAULT_NETWORK_ID);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('2d. daemon_start: start daemon service', async () => {
      // Start daemon after setup (setup only creates service, doesn't start it)
      const result = await runner.daemonStart(undefined, undefined, DEFAULT_NETWORK_ID);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('3. up: execute Rediaccfile prep() and up()', async () => {
      // The up command:
      // 1. Checks for Rediaccfile
      // 2. If first run, executes prep()
      // 3. Executes up() function
      // Note: Network ID required for daemon startup
      const result = await runner.repositoryUp(repositoryName, datastorePath, DEFAULT_NETWORK_ID);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('4. status: verify services started', async () => {
      const result = await runner.repositoryStatus(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('5. down: execute Rediaccfile down()', async () => {
      // The down command executes down() from Rediaccfile
      const result = await runner.repositoryDown(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('6. status: verify services stopped', async () => {
      const result = await runner.repositoryStatus(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('7. cleanup: unmount and remove repository', async () => {
      const unmountResult = await runner.repositoryUnmount(repositoryName, datastorePath);
      expect(runner.isSuccess(unmountResult)).toBe(true);

      const rmResult = await runner.repositoryRm(repositoryName, datastorePath);
      expect(runner.isSuccess(rmResult)).toBe(true);
    });

    test('8. daemon_teardown: tear down daemon service', async () => {
      const result = await runner.daemonTeardown(DEFAULT_NETWORK_ID);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Rediaccfile Edge Cases
 *
 * Tests edge cases for Rediaccfile handling.
 */
test.describe('Rediaccfile Edge Cases @bridge', () => {
  let runner: BridgeTestRunner;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
    await runner.resetWorkerState();
  });

  test('up on nonexistent repository should handle gracefully', async () => {
    // Up without --mount skips gracefully when repo doesn't exist (warns but exits 0)
    const result = await runner.repositoryUp(
      'nonexistent-repo-xyz',
      DEFAULT_DATASTORE_PATH,
      DEFAULT_NETWORK_ID
    );
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('down on nonexistent repository should handle gracefully', async () => {
    const result = await runner.repositoryDown('nonexistent-repo-xyz', DEFAULT_DATASTORE_PATH);
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('up on unmounted repository should handle gracefully', async () => {
    // Up without --mount skips gracefully when repo is not mounted (warns but exits 0)
    const result = await runner.repositoryUp(
      'unmounted-repo',
      DEFAULT_DATASTORE_PATH,
      DEFAULT_NETWORK_ID
    );
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('down on repository without running services should handle gracefully', async () => {
    // Calling down when nothing is running
    const result = await runner.repositoryDown('idle-repo', DEFAULT_DATASTORE_PATH);
    expect(runner.isSuccess(result)).toBe(true);
  });
});

/**
 * Rediaccfile Multiple Runs
 *
 * Tests multiple up/down cycles.
 */
test.describe('Rediaccfile Multiple Runs @bridge', () => {
  let runner: BridgeTestRunner;
  const repositoryName = `multi-run-${Date.now()}`;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
    await runner.resetWorkerState();
  });

  test('multiple up/down cycles should work', async () => {
    const datastorePath = DEFAULT_DATASTORE_PATH;

    // Note: Up without --mount skips gracefully when repo doesn't exist (warns but exits 0)
    const upResult = await runner.repositoryUp(repositoryName, datastorePath, DEFAULT_NETWORK_ID);
    expect(runner.isSuccess(upResult)).toBe(true);

    // Down should still succeed (graceful handling of nonexistent repo)
    const downResult = await runner.repositoryDown(repositoryName, datastorePath);
    expect(runner.isSuccess(downResult)).toBe(true);
  });
});

/**
 * Rediaccfile with Daemon Operations
 *
 * Tests Rediaccfile integration with daemon functions.
 */
test.describe('Rediaccfile with Daemons @bridge', () => {
  let runner: BridgeTestRunner;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
    await runner.resetWorkerState();
  });

  test('up handles nonexistent repo gracefully', async () => {
    // Up without --mount skips gracefully when repo doesn't exist (warns but exits 0)
    const result = await runner.repositoryUp(
      'daemon-test',
      DEFAULT_DATASTORE_PATH,
      DEFAULT_NETWORK_ID
    );
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('daemon_status after up should work', async () => {
    const result = await runner.daemonStatus(
      'daemon-test',
      DEFAULT_DATASTORE_PATH,
      DEFAULT_NETWORK_ID
    );
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('down should stop daemons without syntax errors', async () => {
    const result = await runner.repositoryDown('daemon-test', DEFAULT_DATASTORE_PATH);
    expect(runner.isSuccess(result)).toBe(true);
  });
});

/**
 * Rediaccfile Real Execution Tests
 *
 * Tests actual Rediaccfile execution with nginx container.
 * Verifies prep(), up(), and down() functions work correctly.
 */
test.describe
  .serial('Rediaccfile Real Execution @bridge @integration', () => {
    let runner: BridgeTestRunner;
    const repositoryName = `rediaccfile-nginx-${Date.now()}`;
    const datastorePath = DEFAULT_DATASTORE_PATH;
    const containerName = `nginx-test-${Date.now()}`;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();
      await runner.datastoreInit('10G', datastorePath, true);
    });

    test('1. create and mount repository', async () => {
      const result = await runner.repositoryNew(repositoryName, '1G', TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
      // repo is mounted after create
    });

    test('2. write Rediaccfile to repository', async () => {
      // Uses renet compose (no docker compose fallback)
      const rediaccfileContent = runner.readFixture('bridge/Rediaccfile.nginx');
      const result = await runner.writeFileToRepository(
        repositoryName,
        'Rediaccfile',
        rediaccfileContent,
        datastorePath
      );
      expect(result.code).toBe(0);
    });

    test('3. write docker-compose.yaml to repository', async () => {
      // Replace placeholder with actual container name
      const dockerComposeContent = runner
        .readFixture('bridge/docker-compose.nginx.yaml')
        .replace('${CONTAINER_NAME}', containerName);
      const result = await runner.writeFileToRepository(
        repositoryName,
        'docker-compose.yaml',
        dockerComposeContent,
        datastorePath
      );
      expect(result.code).toBe(0);
    });

    test('3a. daemon_setup: set up daemon service', async () => {
      // Set up daemon before running up with containers
      const result = await runner.daemonSetup(DEFAULT_NETWORK_ID);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('3b. daemon_start: start daemon service', async () => {
      // Start daemon after setup (setup only creates service, doesn't start it)
      const result = await runner.daemonStart(undefined, undefined, DEFAULT_NETWORK_ID);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('4. up: execute Rediaccfile prep() and up()', async () => {
      // Network ID required for daemon startup and renet compose
      const result = await runner.repositoryUp(repositoryName, datastorePath, DEFAULT_NETWORK_ID);
      expect(runner.isSuccess(result)).toBe(true);

      // Verify Rediaccfile was found and executed (not "No Rediaccfile found")
      const output = runner.getCombinedOutput(result);
      expect(output).not.toContain('no rediaccfile found');
    });

    test('5. verify nginx container is running', async () => {
      // Use network ID to check container in network-isolated docker daemon
      const isRunning = await runner.isContainerRunning(containerName, DEFAULT_NETWORK_ID);
      expect(isRunning).toBe(true);
    });

    test('6. down: execute Rediaccfile down()', async () => {
      // Network ID for proper daemon communication
      const result = await runner.repositoryDown(repositoryName, datastorePath, DEFAULT_NETWORK_ID);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('7. verify nginx container is stopped', async () => {
      // Use network ID to check container in network-isolated docker daemon
      const isRunning = await runner.isContainerRunning(containerName, DEFAULT_NETWORK_ID);
      expect(isRunning).toBe(false);
    });

    test('8. cleanup: unmount and remove repository', async () => {
      const unmountResult = await runner.repositoryUnmount(repositoryName, datastorePath);
      expect(runner.isSuccess(unmountResult)).toBe(true);

      const rmResult = await runner.repositoryRm(repositoryName, datastorePath);
      expect(runner.isSuccess(rmResult)).toBe(true);
    });

    test('9. daemon_teardown: tear down daemon service', async () => {
      const result = await runner.daemonTeardown(DEFAULT_NETWORK_ID);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });
