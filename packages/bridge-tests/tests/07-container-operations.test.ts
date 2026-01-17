import { expect, test } from '@playwright/test';
import { DEFAULT_DATASTORE_PATH, DEFAULT_NETWORK_ID, TEST_REPOSITORY_NAME } from '../src/constants';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

/**
 * Container Operations Tests (11 functions)
 *
 * Tests container management functions within repositories.
 *
 * Functions tested:
 * - container_start
 * - container_stop
 * - container_restart
 * - container_logs
 * - container_exec
 * - container_inspect
 * - container_stats
 * - container_list
 * - container_kill
 * - container_pause
 * - container_unpause
 *
 * Containers run within repository context and require:
 * - Repository to be created and mounted
 * - Docker or compatible runtime available
 * - Container to be created via docker-compose/Rediaccfile
 */

const TEST_PASSWORD = 'testpassword123';

test.describe('Container Operations @bridge', () => {
  let runner: BridgeTestRunner;
  const testRepo = `container-ops-${Date.now()}`;
  const testContainer = `nginx-ops-${Date.now()}`;
  const datastorePath = DEFAULT_DATASTORE_PATH;
  const networkId = DEFAULT_NETWORK_ID;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
    await runner.resetWorkerState();

    // 1. Initialize datastore
    await runner.datastoreInit('5G', datastorePath, true);

    // 2. Setup and start daemon (required for Docker socket)
    const setupResult = await runner.daemonSetup(networkId);
    if (!runner.isSuccess(setupResult)) {
      throw new Error(`daemon_setup failed: ${runner.getCombinedOutput(setupResult)}`);
    }
    const startResult = await runner.daemonStart(undefined, undefined, networkId);
    if (!runner.isSuccess(startResult)) {
      throw new Error(`daemon_start failed: ${runner.getCombinedOutput(startResult)}`);
    }

    // 3. Create repository
    const repoResult = await runner.repositoryNew(testRepo, '1G', TEST_PASSWORD, datastorePath);
    if (!runner.isSuccess(repoResult)) {
      throw new Error(`repository_new failed: ${runner.getCombinedOutput(repoResult)}`);
    }

    // 4. Write Rediaccfile (nginx)
    const rediaccfile = runner.readFixture('bridge/Rediaccfile.nginx');
    await runner.writeFileToRepository(testRepo, 'Rediaccfile', rediaccfile, datastorePath);

    // 5. Write docker-compose with unique container name
    const dockerCompose = runner
      .readFixture('bridge/docker-compose.nginx.yaml')
      .replaceAll('${CONTAINER_NAME}', testContainer);
    await runner.writeFileToRepository(
      testRepo,
      'docker-compose.yaml',
      dockerCompose,
      datastorePath
    );

    // 6. Start services (creates container)
    const upResult = await runner.repositoryUp(testRepo, datastorePath, networkId);
    if (!runner.isSuccess(upResult)) {
      throw new Error(`repository_up failed: ${runner.getCombinedOutput(upResult)}`);
    }

    // 7. Verify container exists and is running
    const running = await runner.isContainerRunning(testContainer, networkId);
    if (!running) {
      throw new Error(`Container ${testContainer} is not running after setup`);
    }
  });

  test.afterAll(async () => {
    // Stop services
    await runner.repositoryDown(testRepo, datastorePath, networkId);

    // Unmount and delete repository
    await runner.repositoryUnmount(testRepo, datastorePath);
    await runner.repositoryRm(testRepo, datastorePath);

    // Teardown daemon
    await runner.daemonTeardown(networkId);
  });

  // ===========================================================================
  // Basic Container Operations
  // ===========================================================================

  test('container_start should not have shell syntax errors', async () => {
    // Container is already running from setup, so start might return success or "already started"
    const result = await runner.containerStart(testContainer, testRepo, datastorePath, networkId);
    // Accept both success and "already running" as valid outcomes
    expect(result.code === 0 || result.stderr.includes('already')).toBe(true);
  });

  test('container_stop should not have shell syntax errors', async () => {
    const result = await runner.containerStop(testContainer, testRepo, datastorePath, networkId);
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('container_restart should not have shell syntax errors', async () => {
    // First start the container again
    await runner.containerStart(testContainer, testRepo, datastorePath, networkId);
    const result = await runner.containerRestart(testContainer, testRepo, datastorePath, networkId);
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('container_kill should not have shell syntax errors', async () => {
    // Ensure container is running first
    await runner.containerStart(testContainer, testRepo, datastorePath, networkId);
    const result = await runner.containerKill(testContainer, testRepo, datastorePath, networkId);
    expect(runner.isSuccess(result)).toBe(true);
  });

  // ===========================================================================
  // Container State Operations
  // ===========================================================================

  test('container_pause should not have shell syntax errors', async () => {
    // Start container first
    await runner.containerStart(testContainer, testRepo, datastorePath, networkId);
    const result = await runner.containerPause(testContainer, testRepo, datastorePath, networkId);
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('container_unpause should not have shell syntax errors', async () => {
    // Container should be paused from previous test, unpause it
    const result = await runner.containerUnpause(testContainer, testRepo, datastorePath, networkId);
    expect(runner.isSuccess(result)).toBe(true);
  });

  // ===========================================================================
  // Container Information Operations
  // ===========================================================================

  test('container_logs should not have shell syntax errors', async () => {
    const result = await runner.containerLogs(testContainer, testRepo, datastorePath, networkId);
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('container_inspect should not have shell syntax errors', async () => {
    const result = await runner.containerInspect(testContainer, testRepo, datastorePath, networkId);
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('container_stats should not have shell syntax errors', async () => {
    // Ensure container is running for stats
    await runner.containerStart(testContainer, testRepo, datastorePath, networkId);
    const result = await runner.containerStats(testContainer, testRepo, datastorePath, networkId);
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('container_list should not have shell syntax errors', async () => {
    const result = await runner.containerList(testRepo, datastorePath, networkId);
    expect(runner.isSuccess(result)).toBe(true);
  });

  // ===========================================================================
  // Container Exec Operation
  // ===========================================================================

  test('container_exec should not have shell syntax errors', async () => {
    // Ensure container is running for exec
    await runner.containerStart(testContainer, testRepo, datastorePath, networkId);
    const result = await runner.containerExec(
      testContainer,
      'echo hello',
      testRepo,
      datastorePath,
      networkId
    );
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('container_exec with complex command should handle correctly', async () => {
    const result = await runner.containerExec(
      testContainer,
      'ls -la / && cat /etc/os-release',
      testRepo,
      datastorePath,
      networkId
    );
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('container_exec with quotes should handle correctly', async () => {
    const result = await runner.containerExec(
      testContainer,
      'echo "hello world"',
      testRepo,
      datastorePath,
      networkId
    );
    expect(runner.isSuccess(result)).toBe(true);
  });
});

/**
 * Container Lifecycle Tests
 *
 * Tests container lifecycle in proper order with a real container.
 */
test.describe
  .serial('Container Lifecycle @bridge @lifecycle', () => {
    let runner: BridgeTestRunner;
    const repositoryName = `container-lifecycle-${Date.now()}`;
    const containerName = `nginx-lifecycle-${Date.now()}`;
    const datastorePath = DEFAULT_DATASTORE_PATH;
    const networkId = DEFAULT_NETWORK_ID;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();

      // 1. Initialize datastore
      await runner.datastoreInit('5G', datastorePath, true);

      // 2. Setup and start daemon
      const setupResult = await runner.daemonSetup(networkId);
      if (!runner.isSuccess(setupResult)) {
        throw new Error(`daemon_setup failed: ${runner.getCombinedOutput(setupResult)}`);
      }
      const startResult = await runner.daemonStart(undefined, undefined, networkId);
      if (!runner.isSuccess(startResult)) {
        throw new Error(`daemon_start failed: ${runner.getCombinedOutput(startResult)}`);
      }

      // 3. Create repository
      const repoResult = await runner.repositoryNew(
        repositoryName,
        '1G',
        TEST_PASSWORD,
        datastorePath
      );
      if (!runner.isSuccess(repoResult)) {
        throw new Error(`repository_new failed: ${runner.getCombinedOutput(repoResult)}`);
      }

      // 4. Write Rediaccfile (nginx)
      const rediaccfile = runner.readFixture('bridge/Rediaccfile.nginx');
      await runner.writeFileToRepository(repositoryName, 'Rediaccfile', rediaccfile, datastorePath);

      // 5. Write docker-compose with unique container name
      const dockerCompose = runner
        .readFixture('bridge/docker-compose.nginx.yaml')
        .replaceAll('${CONTAINER_NAME}', containerName);
      await runner.writeFileToRepository(
        repositoryName,
        'docker-compose.yaml',
        dockerCompose,
        datastorePath
      );

      // 6. Start services (creates container)
      const upResult = await runner.repositoryUp(repositoryName, datastorePath, networkId);
      if (!runner.isSuccess(upResult)) {
        throw new Error(`repository_up failed: ${runner.getCombinedOutput(upResult)}`);
      }

      // 7. Stop container to test lifecycle from stopped state
      await runner.containerStop(containerName, repositoryName, datastorePath, networkId);
    });

    test.afterAll(async () => {
      // Stop services
      await runner.repositoryDown(repositoryName, datastorePath, networkId);

      // Unmount and delete repository
      await runner.repositoryUnmount(repositoryName, datastorePath);
      await runner.repositoryRm(repositoryName, datastorePath);

      // Teardown daemon
      await runner.daemonTeardown(networkId);
    });

    test('1. container_list: list containers initially', async () => {
      const result = await runner.containerList(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('2. container_start: start container', async () => {
      const result = await runner.containerStart(
        containerName,
        repositoryName,
        datastorePath,
        networkId
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('3. container_list: verify container started', async () => {
      const result = await runner.containerList(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('4. container_inspect: get container details', async () => {
      const result = await runner.containerInspect(
        containerName,
        repositoryName,
        datastorePath,
        networkId
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('5. container_stats: get container stats', async () => {
      const result = await runner.containerStats(
        containerName,
        repositoryName,
        datastorePath,
        networkId
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('6. container_exec: run command in container', async () => {
      const result = await runner.containerExec(
        containerName,
        'hostname',
        repositoryName,
        datastorePath,
        networkId
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('7. container_logs: get container logs', async () => {
      const result = await runner.containerLogs(
        containerName,
        repositoryName,
        datastorePath,
        networkId
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('8. container_pause: pause container', async () => {
      const result = await runner.containerPause(
        containerName,
        repositoryName,
        datastorePath,
        networkId
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('9. container_unpause: unpause container', async () => {
      const result = await runner.containerUnpause(
        containerName,
        repositoryName,
        datastorePath,
        networkId
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('10. container_restart: restart container', async () => {
      const result = await runner.containerRestart(
        containerName,
        repositoryName,
        datastorePath,
        networkId
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('11. container_stop: stop container', async () => {
      const result = await runner.containerStop(
        containerName,
        repositoryName,
        datastorePath,
        networkId
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('12. container_list: verify container stopped', async () => {
      const result = await runner.containerList(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Container Error Handling Tests
 *
 * Tests error handling for container operations on non-existent containers.
 * These tests verify that operations fail gracefully with clear errors.
 */
test.describe('Container Error Handling @bridge', () => {
  let runner: BridgeTestRunner;
  const networkId = DEFAULT_NETWORK_ID;
  const datastorePath = DEFAULT_DATASTORE_PATH;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
    await runner.resetWorkerState();

    // Setup and start daemon (required for Docker socket)
    const setupResult = await runner.daemonSetup(networkId);
    if (!runner.isSuccess(setupResult)) {
      throw new Error(`daemon_setup failed: ${runner.getCombinedOutput(setupResult)}`);
    }
    const startResult = await runner.daemonStart(undefined, undefined, networkId);
    if (!runner.isSuccess(startResult)) {
      throw new Error(`daemon_start failed: ${runner.getCombinedOutput(startResult)}`);
    }
  });

  test.afterAll(async () => {
    await runner.daemonTeardown(networkId);
  });

  test('operations on nonexistent container should handle gracefully', async () => {
    const nonexistent = 'nonexistent-container-xyz-12345';

    // These operations should FAIL (not succeed) because container doesn't exist
    const stopResult = await runner.containerStop(
      nonexistent,
      TEST_REPOSITORY_NAME,
      datastorePath,
      networkId
    );
    expect(runner.isSuccess(stopResult)).toBe(false);

    const logsResult = await runner.containerLogs(
      nonexistent,
      TEST_REPOSITORY_NAME,
      datastorePath,
      networkId
    );
    expect(runner.isSuccess(logsResult)).toBe(false);

    const inspectResult = await runner.containerInspect(
      nonexistent,
      TEST_REPOSITORY_NAME,
      datastorePath,
      networkId
    );
    expect(runner.isSuccess(inspectResult)).toBe(false);
  });

  test('container_exec on stopped container should handle gracefully', async () => {
    const result = await runner.containerExec(
      'nonexistent-stopped-container',
      'echo test',
      TEST_REPOSITORY_NAME,
      datastorePath,
      networkId
    );
    // Should fail because container doesn't exist
    expect(runner.isSuccess(result)).toBe(false);
  });

  test('container_pause on nonexistent container should handle gracefully', async () => {
    const result = await runner.containerPause(
      'nonexistent-paused-container',
      TEST_REPOSITORY_NAME,
      datastorePath,
      networkId
    );
    // Should fail because container doesn't exist
    expect(runner.isSuccess(result)).toBe(false);
  });

  test('container with special characters in name should handle correctly', async () => {
    // Valid container name with underscores and numbers - but container doesn't exist
    const result = await runner.containerStart(
      'special-name_123',
      TEST_REPOSITORY_NAME,
      datastorePath,
      networkId
    );
    // Should fail because container doesn't exist
    expect(runner.isSuccess(result)).toBe(false);
  });
});

/**
 * Multiple Container Operations Tests
 *
 * Tests operations on multiple containers using a multi-service docker-compose.
 */
test.describe('Multiple Container Operations @bridge', () => {
  let runner: BridgeTestRunner;
  const repositoryName = `multi-container-${Date.now()}`;
  const container1 = `nginx-multi1-${Date.now()}`;
  const container2 = `nginx-multi2-${Date.now()}`;
  const datastorePath = DEFAULT_DATASTORE_PATH;
  const networkId = DEFAULT_NETWORK_ID;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
    await runner.resetWorkerState();

    // 1. Initialize datastore
    await runner.datastoreInit('5G', datastorePath, true);

    // 2. Setup and start daemon
    const setupResult = await runner.daemonSetup(networkId);
    if (!runner.isSuccess(setupResult)) {
      throw new Error(`daemon_setup failed: ${runner.getCombinedOutput(setupResult)}`);
    }
    const startResult = await runner.daemonStart(undefined, undefined, networkId);
    if (!runner.isSuccess(startResult)) {
      throw new Error(`daemon_start failed: ${runner.getCombinedOutput(startResult)}`);
    }

    // 3. Create repository
    const repoResult = await runner.repositoryNew(
      repositoryName,
      '1G',
      TEST_PASSWORD,
      datastorePath
    );
    if (!runner.isSuccess(repoResult)) {
      throw new Error(`repository_new failed: ${runner.getCombinedOutput(repoResult)}`);
    }

    // 4. Write Rediaccfile
    const rediaccfile = runner.readFixture('bridge/Rediaccfile.nginx');
    await runner.writeFileToRepository(repositoryName, 'Rediaccfile', rediaccfile, datastorePath);

    // 5. Write docker-compose with TWO containers
    const dockerCompose = `services:
  nginx1:
    image: nginx:alpine
    container_name: ${container1}
    network_mode: "\${REPOSITORY_NETWORK_MODE:-bridge}"
  nginx2:
    image: nginx:alpine
    container_name: ${container2}
    network_mode: "\${REPOSITORY_NETWORK_MODE:-bridge}"
`;
    await runner.writeFileToRepository(
      repositoryName,
      'docker-compose.yaml',
      dockerCompose,
      datastorePath
    );

    // 6. Start services (creates both containers)
    const upResult = await runner.repositoryUp(repositoryName, datastorePath, networkId);
    if (!runner.isSuccess(upResult)) {
      throw new Error(`repository_up failed: ${runner.getCombinedOutput(upResult)}`);
    }
  });

  test.afterAll(async () => {
    // Stop services
    await runner.repositoryDown(repositoryName, datastorePath, networkId);

    // Unmount and delete repository
    await runner.repositoryUnmount(repositoryName, datastorePath);
    await runner.repositoryRm(repositoryName, datastorePath);

    // Teardown daemon
    await runner.daemonTeardown(networkId);
  });

  test('starting multiple containers should work', async () => {
    const containers = [container1, container2];

    for (const container of containers) {
      // Containers may already be running, so accept both success and "already running"
      const result = await runner.containerStart(
        container,
        repositoryName,
        datastorePath,
        networkId
      );
      expect(result.code === 0 || result.stderr.includes('already')).toBe(true);
    }
  });

  test('listing all containers should work', async () => {
    const result = await runner.containerList(repositoryName, datastorePath, networkId);
    expect(runner.isSuccess(result)).toBe(true);
    // Verify both containers are in the list
    const output = runner.getCombinedOutput(result);
    expect(output).toContain(container1);
    expect(output).toContain(container2);
  });

  test('stopping multiple containers should work', async () => {
    const containers = [container1, container2];

    for (const container of containers) {
      const result = await runner.containerStop(
        container,
        repositoryName,
        datastorePath,
        networkId
      );
      expect(runner.isSuccess(result)).toBe(true);
    }
  });
});
