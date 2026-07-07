import { expect, test } from '@playwright/test';
import { DEFAULT_DATASTORE_PATH, DEFAULT_NETWORK_ID, TEST_PASSWORD } from '../src/constants';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

/**
 * Full Repository Workflow
 *
 * Tests a complete repository lifecycle from creation to deletion.
 * This includes system checks, repository creation, mounting, services,
 * resize operations, and cleanup.
 */
test.describe
  .serial('Full Repository Workflow @bridge @integration', () => {
    let runner: BridgeTestRunner;
    const repositoryName = `full-workflow-${Date.now()}`;
    const datastorePath = DEFAULT_DATASTORE_PATH;

    test.beforeAll(() => {
      runner = BridgeTestRunner.forWorker();
    });

    test.afterAll(async () => {
      // Cleanup: ensure repository is unmounted and deleted even if tests fail
      try {
        await runner.repositoryUnmount(repositoryName, datastorePath);
      } catch {
        /* ignore */
      }
      try {
        await runner.repositoryRm(repositoryName, datastorePath);
      } catch {
        /* ignore */
      }
    });

    // Phase 1: System Checks
    test('1.1 ping: verify system connectivity', async () => {
      const result = await runner.ping();
      expect(result.code).toBe(0);
      expect(runner.getCombinedOutput(result)).toContain('pong');
    });

    test('1.2 check_system: verify system requirements', async () => {
      const result = await runner.checkSystem();
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('1.3 check_datastore: verify datastore available', async () => {
      const result = await runner.checkDatastore(datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Phase 2: Repository Creation
    test('2.1 new: create repository', async () => {
      const result = await runner.repositoryNew(
        repositoryName,
        '500M',
        TEST_PASSWORD,
        datastorePath
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('2.2 list: verify repository created', async () => {
      const result = await runner.repositoryList(datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('2.3 info: get repository info', async () => {
      const result = await runner.repositoryInfo(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Phase 3: Mount and Use
    test('3.1 mount: mount repository', async () => {
      const result = await runner.repositoryMount(repositoryName, TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('3.2 status: check mounted status', async () => {
      const result = await runner.repositoryStatus(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('3.3 validate: validate mounted repository', async () => {
      const result = await runner.repositoryValidate(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Phase 4: Rediaccfile Operations
    test('4.1 up: start repository services', async () => {
      const result = await runner.repositoryUp(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('4.2 status: verify services running', async () => {
      const result = await runner.repositoryStatus(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('4.3 down: stop repository services', async () => {
      const result = await runner.repositoryDown(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Phase 5: Resize (requires unmounted repo)
    test('5.1 unmount: unmount for resize', async () => {
      const result = await runner.repositoryUnmount(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('5.2 resize: expand repository', async () => {
      const result = await runner.repositoryResize(
        repositoryName,
        '1G',
        TEST_PASSWORD,
        datastorePath
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Phase 6: Cleanup (already unmounted from resize)
    test('6.1 rm: delete repository', async () => {
      const result = await runner.repositoryRm(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Container + Repository Integration
 *
 * Tests containers within the repository context.
 */
test.describe
  .serial('Container Repository Integration @bridge @integration', () => {
    let runner: BridgeTestRunner;
    const repositoryName = `container-integration-${Date.now()}`;
    const containerName = 'test-nginx';
    const datastorePath = DEFAULT_DATASTORE_PATH;
    const networkId = DEFAULT_NETWORK_ID;

    test.beforeAll(() => {
      runner = BridgeTestRunner.forWorker();
    });

    test.afterAll(async () => {
      // Cleanup: ensure repository is unmounted and deleted even if tests fail
      try {
        await runner.repositoryDown(repositoryName, datastorePath, networkId);
      } catch {
        /* ignore */
      }
      try {
        await runner.repositoryUnmount(repositoryName, datastorePath);
      } catch {
        /* ignore */
      }
      try {
        await runner.repositoryRm(repositoryName, datastorePath);
      } catch {
        /* ignore */
      }
    });

    // Setup repository
    test('1. create repository', async () => {
      const result = await runner.repositoryNew(
        repositoryName,
        '500M',
        TEST_PASSWORD,
        datastorePath
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('2. mount repository', async () => {
      const result = await runner.repositoryMount(repositoryName, TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Write Rediaccfile and docker-compose.yaml for container setup
    test('2.1 write Rediaccfile', async () => {
      const rediaccfileContent = runner.readFixture('bridge/Rediaccfile.nginx');
      await runner.writeFileToRepository(
        repositoryName,
        'Rediaccfile',
        rediaccfileContent,
        datastorePath
      );
    });

    test('2.2 write docker-compose.yaml', async () => {
      const dockerComposeContent = runner
        .readFixture('bridge/docker-compose.nginx.yaml')
        .replaceAll('${CONTAINER_NAME}', containerName);
      await runner.writeFileToRepository(
        repositoryName,
        'docker-compose.yaml',
        dockerComposeContent,
        datastorePath
      );
    });

    // Setup and start daemon first (required for container operations)
    test('2a. daemon_setup: set up daemon service', async () => {
      // daemonSetup only takes networkId as parameter
      const result = await runner.daemonSetup(networkId.toString());
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('2b. daemon_start: start daemon service', async () => {
      // daemonStart takes (repository, datastorePath, networkId)
      const result = await runner.daemonStart(repositoryName, datastorePath, networkId.toString());
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Start services (which starts containers)
    test('3. up: start repository services', async () => {
      const result = await runner.repositoryUp(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Container operations
    test('4. list containers', async () => {
      const result = await runner.containerList(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('5. start container', async () => {
      const result = await runner.containerStart(
        containerName,
        repositoryName,
        datastorePath,
        networkId
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('6. inspect container', async () => {
      const result = await runner.containerInspect(
        containerName,
        repositoryName,
        datastorePath,
        networkId
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('7. get container logs', async () => {
      const result = await runner.containerLogs(
        containerName,
        repositoryName,
        datastorePath,
        networkId
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('8. stop container', async () => {
      const result = await runner.containerStop(
        containerName,
        repositoryName,
        datastorePath,
        networkId
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Cleanup
    test('9. down: stop repository services', async () => {
      const result = await runner.repositoryDown(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('10. unmount repository', async () => {
      const result = await runner.repositoryUnmount(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('11. delete repository', async () => {
      const result = await runner.repositoryRm(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Error Recovery Integration
 *
 * Tests graceful error handling and recovery.
 */
test.describe('Error Recovery Integration @bridge @integration', () => {
  let runner: BridgeTestRunner;

  test.beforeAll(() => {
    runner = BridgeTestRunner.forWorker();
  });

  test('should handle sequential operations on nonexistent resources', async () => {
    const nonexistent = 'nonexistent-resource-xyz';

    // Run operations on nonexistent resources - they should fail gracefully (no crashes/syntax errors)
    // Some operations are strict (fail if resource doesn't exist), others are tolerant (succeed as no-op)
    const [info, mount, up, down, unmount, rm] = await Promise.all([
      runner.repositoryInfo(nonexistent, DEFAULT_DATASTORE_PATH),
      runner.repositoryMount(nonexistent, TEST_PASSWORD, DEFAULT_DATASTORE_PATH),
      runner.repositoryUp(nonexistent, DEFAULT_DATASTORE_PATH),
      runner.repositoryDown(nonexistent, DEFAULT_DATASTORE_PATH),
      runner.repositoryUnmount(nonexistent, DEFAULT_DATASTORE_PATH),
      runner.repositoryRm(nonexistent, DEFAULT_DATASTORE_PATH),
    ]);

    // Strict operations - should fail because resource doesn't exist
    expect(runner.isSuccess(info)).toBe(false); // Can't get info on nonexistent
    expect(runner.isSuccess(mount)).toBe(false); // Can't mount nonexistent
    expect(runner.isSuccess(rm)).toBe(false); // Can't delete nonexistent

    // Tolerant operations - succeed as no-op (nothing to do)
    expect(runner.isSuccess(up)).toBe(true); // No Rediaccfile, skips gracefully
    expect(runner.isSuccess(down)).toBe(true); // Nothing to stop, succeeds
    expect(runner.isSuccess(unmount)).toBe(true); // Already unmounted, succeeds
  });

  test('should recover from failed operation', async () => {
    // Attempt an operation that will fail (mounting nonexistent repository)
    const failResult = await runner.repositoryMount(
      'likely-nonexistent',
      TEST_PASSWORD,
      DEFAULT_DATASTORE_PATH
    );
    expect(runner.isSuccess(failResult)).toBe(false); // Mount should fail

    // System should still be responsive after the failed operation
    const pingResult = await runner.ping();
    expect(pingResult.code).toBe(0);
    expect(runner.getCombinedOutput(pingResult)).toContain('pong');
  });
});
