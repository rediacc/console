import { expect, test } from '@playwright/test';
import {
  DEFAULT_DATASTORE_PATH,
  DEFAULT_NETWORK_ID,
  FORK_NETWORK_ID_A,
  FORK_NETWORK_ID_B,
  TEST_PASSWORD,
} from '../src/constants';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

/**
 * PostgreSQL Fork Isolation Tests
 *
 * Tests the core rediacc value proposition: fork repositories with data,
 * ensuring forks are truly independent copies.
 *
 * This test suite validates:
 * 1. Data persistence across mount/unmount cycles
 * 2. Fork creation and data inheritance
 * 3. Fork independence (changes in fork don't affect parent)
 * 4. Bidirectional isolation (changes in parent don't affect fork)
 * 5. Multiple forks from same parent
 * 6. Data integrity verification with checksums
 * 7. Large data volume handling
 * 8. Service restart persistence
 *
 * Network IDs:
 * - Parent: 9152 (DEFAULT_NETWORK_ID)
 * - Fork A: 9216 (FORK_NETWORK_ID_A)
 * - Fork B: 9280 (FORK_NETWORK_ID_B)
 */

// ===========================================================================
// Scenario 1: Basic Data Persistence (Sanity Check)
// ===========================================================================

test.describe
  .serial('PostgreSQL Data Persistence @bridge @integration', () => {
    let runner: BridgeTestRunner;
    const repositoryName = `postgres-persist-${Date.now()}`;
    const containerName = `postgres-persist-${Date.now()}`;
    const datastorePath = DEFAULT_DATASTORE_PATH;
    const networkId = DEFAULT_NETWORK_ID;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();
      await runner.datastoreInit('10G', datastorePath, true);
      // Setup and start daemon for Docker operations
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

    test('1. create and mount repository', async () => {
      const result = await runner.repositoryNew(repositoryName, '2G', TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('2. write Rediaccfile.postgresql to repository', async () => {
      const rediaccfileContent = runner.readFixture('bridge/Rediaccfile.postgresql');
      const result = await runner.writeFileToRepository(
        repositoryName,
        'Rediaccfile',
        rediaccfileContent,
        datastorePath
      );
      expect(result.code).toBe(0);
    });

    test('3. write docker-compose.postgresql.yaml to repository', async () => {
      const dockerComposeContent = runner
        .readFixture('bridge/docker-compose.postgresql.yaml')
        .replaceAll('${CONTAINER_NAME}', containerName);
      const result = await runner.writeFileToRepository(
        repositoryName,
        'docker-compose.yaml',
        dockerComposeContent,
        datastorePath
      );
      expect(result.code).toBe(0);
    });

    test('4. write init-postgres.sql to repository', async () => {
      const initSqlContent = runner.readFixture('bridge/init-postgres.sql');
      const result = await runner.writeFileToRepository(
        repositoryName,
        'init-postgres.sql',
        initSqlContent,
        datastorePath
      );
      expect(result.code).toBe(0);
    });

    test('5. up: start PostgreSQL container', async () => {
      const result = await runner.repositoryUp(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('6. wait for PostgreSQL and verify seed data', async () => {
      // Wait for PostgreSQL to be fully ready (not just accepting connections)
      // PostgreSQL may briefly accept connections during init, then restart
      // So we combine waiting and verification in a single test to avoid race conditions
      const ready = await runner.waitForPostgresReady(containerName, networkId);
      expect(ready).toBe(true);

      // Small delay to ensure init scripts have completed
      await new Promise((resolve) => setTimeout(resolve, 2000));

      const seedExists = await runner.recordExistsByOrigin(containerName, 'seed', networkId);
      expect(seedExists).toBe(true);

      const count = await runner.getUserRecordCount(containerName, networkId);
      expect(count).toBe(3); // alice, bob, charlie
    });

    test('7. insert test record', async () => {
      await runner.insertUserRecord(containerName, 'persist_user', 'persist-test', networkId);
      const exists = await runner.recordExistsByOrigin(containerName, 'persist-test', networkId);
      expect(exists).toBe(true);
    });

    test('8. down: stop PostgreSQL services', async () => {
      const result = await runner.repositoryDown(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('9. unmount repository', async () => {
      const result = await runner.repositoryUnmount(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('10. mount repository again', async () => {
      const result = await runner.repositoryMount(repositoryName, TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('11. up: start PostgreSQL again', async () => {
      const result = await runner.repositoryUp(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('12. wait for PostgreSQL and verify data persisted', async () => {
      // Wait for PostgreSQL to be fully ready after remount
      const ready = await runner.waitForPostgresReady(containerName, networkId);
      expect(ready).toBe(true);

      // Small delay to ensure PostgreSQL is fully operational
      await new Promise((resolve) => setTimeout(resolve, 2000));

      // Check seed data still exists
      const seedExists = await runner.recordExistsByOrigin(containerName, 'seed', networkId);
      expect(seedExists).toBe(true);

      // Check our inserted record still exists
      const persistExists = await runner.recordExistsByOrigin(
        containerName,
        'persist-test',
        networkId
      );
      expect(persistExists).toBe(true);

      // Total should be 4 (3 seed + 1 inserted)
      const count = await runner.getUserRecordCount(containerName, networkId);
      expect(count).toBe(4);
    });

    test('13. cleanup', async () => {
      await runner.repositoryDown(repositoryName, datastorePath, networkId);
      await runner.repositoryUnmount(repositoryName, datastorePath);
      await runner.repositoryRm(repositoryName, datastorePath);
    });
  });

// ===========================================================================
// Scenarios 2-4: Fork Creation, Inheritance, and Independence
// ===========================================================================

test.describe
  .serial('Repository Fork Data Inheritance @bridge @integration', () => {
    let runner: BridgeTestRunner;
    const parentRepoName = `postgres-parent-${Date.now()}`;
    const forkRepoName = `postgres-fork-${Date.now()}`;
    const parentContainerName = `postgres-parent-${Date.now()}`;
    const forkContainerName = `postgres-fork-${Date.now()}`;
    const datastorePath = DEFAULT_DATASTORE_PATH;
    const parentNetworkId = DEFAULT_NETWORK_ID;
    const forkNetworkId = FORK_NETWORK_ID_A;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();
      await runner.datastoreInit('12G', datastorePath, true);
      // Setup and start daemons for both network IDs (parent and fork)
      for (const netId of [parentNetworkId, forkNetworkId]) {
        const setupResult = await runner.daemonSetup(netId);
        if (!runner.isSuccess(setupResult)) {
          throw new Error(
            `daemon_setup failed for ${netId}: ${runner.getCombinedOutput(setupResult)}`
          );
        }
        const startResult = await runner.daemonStart(undefined, undefined, netId);
        if (!runner.isSuccess(startResult)) {
          throw new Error(
            `daemon_start failed for ${netId}: ${runner.getCombinedOutput(startResult)}`
          );
        }
      }
    });

    test.afterAll(async () => {
      await runner.daemonTeardown(forkNetworkId);
      await runner.daemonTeardown(parentNetworkId);
    });

    // --- Scenario 2: Create parent and insert unique data ---

    test('1. create parent repository', async () => {
      const result = await runner.repositoryNew(parentRepoName, '1G', TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('2. write PostgreSQL files to parent repository', async () => {
      const rediaccfileContent = runner.readFixture('bridge/Rediaccfile.postgresql');
      await runner.writeFileToRepository(
        parentRepoName,
        'Rediaccfile',
        rediaccfileContent,
        datastorePath
      );

      const dockerComposeContent = runner
        .readFixture('bridge/docker-compose.postgresql.yaml')
        .replaceAll('${CONTAINER_NAME}', parentContainerName);
      await runner.writeFileToRepository(
        parentRepoName,
        'docker-compose.yaml',
        dockerComposeContent,
        datastorePath
      );

      const initSqlContent = runner.readFixture('bridge/init-postgres.sql');
      await runner.writeFileToRepository(
        parentRepoName,
        'init-postgres.sql',
        initSqlContent,
        datastorePath
      );
    });

    test('3. start parent PostgreSQL', async () => {
      const result = await runner.repositoryUp(parentRepoName, datastorePath, parentNetworkId);
      expect(runner.isSuccess(result)).toBe(true);

      const ready = await runner.waitForPostgresReady(parentContainerName, parentNetworkId);
      expect(ready).toBe(true);
    });

    test('4. insert parent-only record', async () => {
      await runner.insertUserRecord(
        parentContainerName,
        'parent_user',
        'parent-only',
        parentNetworkId
      );
      const exists = await runner.recordExistsByOrigin(
        parentContainerName,
        'parent-only',
        parentNetworkId
      );
      expect(exists).toBe(true);
    });

    test('5. stop parent services for forking', async () => {
      const result = await runner.repositoryDown(parentRepoName, datastorePath, parentNetworkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('6. unmount parent for forking', async () => {
      const result = await runner.repositoryUnmount(parentRepoName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('7. create fork by copying parent repository', async () => {
      const result = await runner.createRepositoryFork(parentRepoName, forkRepoName, datastorePath);
      expect(result.code).toBe(0);

      const exists = await runner.repositoryExists(forkRepoName, datastorePath);
      expect(exists).toBe(true);
    });

    test('8. mount fork repository', async () => {
      const result = await runner.repositoryMount(forkRepoName, TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('9. update fork docker-compose with new container name', async () => {
      // Must update container name to avoid conflicts
      const dockerComposeContent = runner
        .readFixture('bridge/docker-compose.postgresql.yaml')
        .replaceAll('${CONTAINER_NAME}', forkContainerName);
      await runner.writeFileToRepository(
        forkRepoName,
        'docker-compose.yaml',
        dockerComposeContent,
        datastorePath
      );
    });

    test('10. start fork PostgreSQL with different network ID', async () => {
      const result = await runner.repositoryUp(forkRepoName, datastorePath, forkNetworkId);
      expect(runner.isSuccess(result)).toBe(true);

      const ready = await runner.waitForPostgresReady(forkContainerName, forkNetworkId);
      expect(ready).toBe(true);
    });

    test('11. verify fork has seed data', async () => {
      const seedExists = await runner.recordExistsByOrigin(
        forkContainerName,
        'seed',
        forkNetworkId
      );
      expect(seedExists).toBe(true);
    });

    test('12. verify fork has parent-only record (data inheritance)', async () => {
      const parentOnlyExists = await runner.recordExistsByOrigin(
        forkContainerName,
        'parent-only',
        forkNetworkId
      );
      expect(parentOnlyExists).toBe(true);

      // Total should be 4 (3 seed + 1 parent-only)
      const count = await runner.getUserRecordCount(forkContainerName, forkNetworkId);
      expect(count).toBe(4);
    });

    // --- Scenario 3: Fork Independence (changes in fork don't affect parent) ---

    test('13. insert fork-only record', async () => {
      await runner.insertUserRecord(forkContainerName, 'fork_user', 'fork-only', forkNetworkId);
      const exists = await runner.recordExistsByOrigin(
        forkContainerName,
        'fork-only',
        forkNetworkId
      );
      expect(exists).toBe(true);

      // Fork should now have 5 records
      const count = await runner.getUserRecordCount(forkContainerName, forkNetworkId);
      expect(count).toBe(5);
    });

    test('14. remount and start parent to verify isolation', async () => {
      const mountResult = await runner.repositoryMount(
        parentRepoName,
        TEST_PASSWORD,
        datastorePath
      );
      expect(runner.isSuccess(mountResult)).toBe(true);

      const upResult = await runner.repositoryUp(parentRepoName, datastorePath, parentNetworkId);
      expect(runner.isSuccess(upResult)).toBe(true);

      const ready = await runner.waitForPostgresReady(parentContainerName, parentNetworkId);
      expect(ready).toBe(true);
    });

    test('15. verify parent does NOT have fork-only record', async () => {
      const forkOnlyExists = await runner.recordExistsByOrigin(
        parentContainerName,
        'fork-only',
        parentNetworkId
      );
      expect(forkOnlyExists).toBe(false);

      // Parent should still have only 4 records
      const count = await runner.getUserRecordCount(parentContainerName, parentNetworkId);
      expect(count).toBe(4);
    });

    // --- Scenario 4: Bidirectional Independence (changes in parent don't affect fork) ---

    test('16. insert parent-after-fork record', async () => {
      await runner.insertUserRecord(
        parentContainerName,
        'parent_after_fork_user',
        'parent-after-fork',
        parentNetworkId
      );
      const exists = await runner.recordExistsByOrigin(
        parentContainerName,
        'parent-after-fork',
        parentNetworkId
      );
      expect(exists).toBe(true);

      // Parent should now have 5 records
      const parentCount = await runner.getUserRecordCount(parentContainerName, parentNetworkId);
      expect(parentCount).toBe(5);
    });

    test('17. verify fork does NOT have parent-after-fork record', async () => {
      const parentAfterForkExists = await runner.recordExistsByOrigin(
        forkContainerName,
        'parent-after-fork',
        forkNetworkId
      );
      expect(parentAfterForkExists).toBe(false);

      // Fork should still have 5 records (3 seed + parent-only + fork-only)
      const forkCount = await runner.getUserRecordCount(forkContainerName, forkNetworkId);
      expect(forkCount).toBe(5);
    });

    test('18. verify final data isolation summary', async () => {
      // Parent has: seed (3) + parent-only (1) + parent-after-fork (1) = 5
      const parentCount = await runner.getUserRecordCount(parentContainerName, parentNetworkId);
      expect(parentCount).toBe(5);

      // Fork has: seed (3) + parent-only (1) + fork-only (1) = 5
      const forkCount = await runner.getUserRecordCount(forkContainerName, forkNetworkId);
      expect(forkCount).toBe(5);

      // But they have DIFFERENT records!
      const parentHasForkOnly = await runner.recordExistsByOrigin(
        parentContainerName,
        'fork-only',
        parentNetworkId
      );
      const forkHasParentAfterFork = await runner.recordExistsByOrigin(
        forkContainerName,
        'parent-after-fork',
        forkNetworkId
      );
      expect(parentHasForkOnly).toBe(false);
      expect(forkHasParentAfterFork).toBe(false);
    });

    test('19. cleanup', async () => {
      // Stop and remove fork
      await runner.repositoryDown(forkRepoName, datastorePath, forkNetworkId);
      await runner.repositoryUnmount(forkRepoName, datastorePath);
      await runner.repositoryRm(forkRepoName, datastorePath);

      // Stop and remove parent
      await runner.repositoryDown(parentRepoName, datastorePath, parentNetworkId);
      await runner.repositoryUnmount(parentRepoName, datastorePath);
      await runner.repositoryRm(parentRepoName, datastorePath);
    });
  });

// ===========================================================================
// Scenario 5: Multiple Forks from Same Parent
// ===========================================================================

test.describe
  .serial('Multiple Fork Independence @bridge @integration', () => {
    let runner: BridgeTestRunner;
    const timestamp = Date.now();
    const parentRepoName = `postgres-multi-parent-${timestamp}`;
    const forkARepoName = `postgres-fork-a-${timestamp}`;
    const forkBRepoName = `postgres-fork-b-${timestamp}`;
    const parentContainerName = `postgres-multi-parent-${timestamp}`;
    const forkAContainerName = `postgres-fork-a-${timestamp}`;
    const forkBContainerName = `postgres-fork-b-${timestamp}`;
    const datastorePath = DEFAULT_DATASTORE_PATH;
    const parentNetworkId = DEFAULT_NETWORK_ID;
    const forkANetworkId = FORK_NETWORK_ID_A;
    const forkBNetworkId = FORK_NETWORK_ID_B;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();
      await runner.datastoreInit('10G', datastorePath, true);
      // Setup and start daemons for all three network IDs (parent and both forks)
      for (const netId of [parentNetworkId, forkANetworkId, forkBNetworkId]) {
        const setupResult = await runner.daemonSetup(netId);
        if (!runner.isSuccess(setupResult)) {
          throw new Error(
            `daemon_setup failed for ${netId}: ${runner.getCombinedOutput(setupResult)}`
          );
        }
        const startResult = await runner.daemonStart(undefined, undefined, netId);
        if (!runner.isSuccess(startResult)) {
          throw new Error(
            `daemon_start failed for ${netId}: ${runner.getCombinedOutput(startResult)}`
          );
        }
      }
    });

    test.afterAll(async () => {
      await runner.daemonTeardown(forkBNetworkId);
      await runner.daemonTeardown(forkANetworkId);
      await runner.daemonTeardown(parentNetworkId);
    });

    test('1. create parent with PostgreSQL', async () => {
      await runner.repositoryNew(parentRepoName, '1G', TEST_PASSWORD, datastorePath);

      const rediaccfileContent = runner.readFixture('bridge/Rediaccfile.postgresql');
      await runner.writeFileToRepository(
        parentRepoName,
        'Rediaccfile',
        rediaccfileContent,
        datastorePath
      );

      const dockerComposeContent = runner
        .readFixture('bridge/docker-compose.postgresql.yaml')
        .replaceAll('${CONTAINER_NAME}', parentContainerName);
      await runner.writeFileToRepository(
        parentRepoName,
        'docker-compose.yaml',
        dockerComposeContent,
        datastorePath
      );

      const initSqlContent = runner.readFixture('bridge/init-postgres.sql');
      await runner.writeFileToRepository(
        parentRepoName,
        'init-postgres.sql',
        initSqlContent,
        datastorePath
      );
    });

    test('2. start parent and verify seed data', async () => {
      await runner.repositoryUp(parentRepoName, datastorePath, parentNetworkId);
      await runner.waitForPostgresReady(parentContainerName, parentNetworkId);

      const count = await runner.getUserRecordCount(parentContainerName, parentNetworkId);
      expect(count).toBe(3);
    });

    test('3. stop and unmount parent for forking', async () => {
      await runner.repositoryDown(parentRepoName, datastorePath, parentNetworkId);
      await runner.repositoryUnmount(parentRepoName, datastorePath);
    });

    test('4. create fork A', async () => {
      await runner.createRepositoryFork(parentRepoName, forkARepoName, datastorePath);
      await runner.repositoryMount(forkARepoName, TEST_PASSWORD, datastorePath);

      const dockerComposeContent = runner
        .readFixture('bridge/docker-compose.postgresql.yaml')
        .replaceAll('${CONTAINER_NAME}', forkAContainerName);
      await runner.writeFileToRepository(
        forkARepoName,
        'docker-compose.yaml',
        dockerComposeContent,
        datastorePath
      );
    });

    test('5. create fork B', async () => {
      await runner.createRepositoryFork(parentRepoName, forkBRepoName, datastorePath);
      await runner.repositoryMount(forkBRepoName, TEST_PASSWORD, datastorePath);

      const dockerComposeContent = runner
        .readFixture('bridge/docker-compose.postgresql.yaml')
        .replaceAll('${CONTAINER_NAME}', forkBContainerName);
      await runner.writeFileToRepository(
        forkBRepoName,
        'docker-compose.yaml',
        dockerComposeContent,
        datastorePath
      );
    });

    test('6. start all three repositories with different network IDs', async () => {
      // Start parent
      await runner.repositoryMount(parentRepoName, TEST_PASSWORD, datastorePath);
      await runner.repositoryUp(parentRepoName, datastorePath, parentNetworkId);
      await runner.waitForPostgresReady(parentContainerName, parentNetworkId);

      // Start fork A
      await runner.repositoryUp(forkARepoName, datastorePath, forkANetworkId);
      await runner.waitForPostgresReady(forkAContainerName, forkANetworkId);

      // Start fork B
      await runner.repositoryUp(forkBRepoName, datastorePath, forkBNetworkId);
      await runner.waitForPostgresReady(forkBContainerName, forkBNetworkId);
    });

    test('7. insert unique data into each repository', async () => {
      await runner.insertUserRecord(
        parentContainerName,
        'parent_unique',
        'parent-post-forks',
        parentNetworkId
      );
      await runner.insertUserRecord(
        forkAContainerName,
        'fork_a_unique',
        'fork-a-only',
        forkANetworkId
      );
      await runner.insertUserRecord(
        forkBContainerName,
        'fork_b_unique',
        'fork-b-only',
        forkBNetworkId
      );
    });

    test('8. verify complete data isolation between all three', async () => {
      // Parent: seed (3) + parent-post-forks (1) = 4
      const parentCount = await runner.getUserRecordCount(parentContainerName, parentNetworkId);
      expect(parentCount).toBe(4);
      expect(
        await runner.recordExistsByOrigin(parentContainerName, 'parent-post-forks', parentNetworkId)
      ).toBe(true);
      expect(
        await runner.recordExistsByOrigin(parentContainerName, 'fork-a-only', parentNetworkId)
      ).toBe(false);
      expect(
        await runner.recordExistsByOrigin(parentContainerName, 'fork-b-only', parentNetworkId)
      ).toBe(false);

      // Fork A: seed (3) + fork-a-only (1) = 4
      const forkACount = await runner.getUserRecordCount(forkAContainerName, forkANetworkId);
      expect(forkACount).toBe(4);
      expect(
        await runner.recordExistsByOrigin(forkAContainerName, 'fork-a-only', forkANetworkId)
      ).toBe(true);
      expect(
        await runner.recordExistsByOrigin(forkAContainerName, 'fork-b-only', forkANetworkId)
      ).toBe(false);
      expect(
        await runner.recordExistsByOrigin(forkAContainerName, 'parent-post-forks', forkANetworkId)
      ).toBe(false);

      // Fork B: seed (3) + fork-b-only (1) = 4
      const forkBCount = await runner.getUserRecordCount(forkBContainerName, forkBNetworkId);
      expect(forkBCount).toBe(4);
      expect(
        await runner.recordExistsByOrigin(forkBContainerName, 'fork-b-only', forkBNetworkId)
      ).toBe(true);
      expect(
        await runner.recordExistsByOrigin(forkBContainerName, 'fork-a-only', forkBNetworkId)
      ).toBe(false);
      expect(
        await runner.recordExistsByOrigin(forkBContainerName, 'parent-post-forks', forkBNetworkId)
      ).toBe(false);
    });

    test('9. cleanup all repositories', async () => {
      // Cleanup fork B
      await runner.repositoryDown(forkBRepoName, datastorePath, forkBNetworkId);
      await runner.repositoryUnmount(forkBRepoName, datastorePath);
      await runner.repositoryRm(forkBRepoName, datastorePath);

      // Cleanup fork A
      await runner.repositoryDown(forkARepoName, datastorePath, forkANetworkId);
      await runner.repositoryUnmount(forkARepoName, datastorePath);
      await runner.repositoryRm(forkARepoName, datastorePath);

      // Cleanup parent
      await runner.repositoryDown(parentRepoName, datastorePath, parentNetworkId);
      await runner.repositoryUnmount(parentRepoName, datastorePath);
      await runner.repositoryRm(parentRepoName, datastorePath);
    });
  });

// ===========================================================================
// Scenario 6: Data Integrity Check
// ===========================================================================

test.describe
  .serial('Fork Data Integrity @bridge @integration', () => {
    let runner: BridgeTestRunner;
    const timestamp = Date.now();
    const parentRepoName = `postgres-integrity-parent-${timestamp}`;
    const forkRepoName = `postgres-integrity-fork-${timestamp}`;
    const parentContainerName = `postgres-integrity-parent-${timestamp}`;
    const forkContainerName = `postgres-integrity-fork-${timestamp}`;
    const datastorePath = DEFAULT_DATASTORE_PATH;
    const parentNetworkId = DEFAULT_NETWORK_ID;
    const forkNetworkId = FORK_NETWORK_ID_A;

    let parentHashBeforeFork: string;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();
      await runner.datastoreInit('10G', datastorePath, true);
      // Setup and start daemons for both network IDs (parent and fork)
      for (const netId of [parentNetworkId, forkNetworkId]) {
        const setupResult = await runner.daemonSetup(netId);
        if (!runner.isSuccess(setupResult)) {
          throw new Error(
            `daemon_setup failed for ${netId}: ${runner.getCombinedOutput(setupResult)}`
          );
        }
        const startResult = await runner.daemonStart(undefined, undefined, netId);
        if (!runner.isSuccess(startResult)) {
          throw new Error(
            `daemon_start failed for ${netId}: ${runner.getCombinedOutput(startResult)}`
          );
        }
      }
    });

    test.afterAll(async () => {
      await runner.daemonTeardown(forkNetworkId);
      await runner.daemonTeardown(parentNetworkId);
    });

    test('1. create parent with PostgreSQL', async () => {
      await runner.repositoryNew(parentRepoName, '1G', TEST_PASSWORD, datastorePath);

      const rediaccfileContent = runner.readFixture('bridge/Rediaccfile.postgresql');
      await runner.writeFileToRepository(
        parentRepoName,
        'Rediaccfile',
        rediaccfileContent,
        datastorePath
      );

      const dockerComposeContent = runner
        .readFixture('bridge/docker-compose.postgresql.yaml')
        .replaceAll('${CONTAINER_NAME}', parentContainerName);
      await runner.writeFileToRepository(
        parentRepoName,
        'docker-compose.yaml',
        dockerComposeContent,
        datastorePath
      );

      const initSqlContent = runner.readFixture('bridge/init-postgres.sql');
      await runner.writeFileToRepository(
        parentRepoName,
        'init-postgres.sql',
        initSqlContent,
        datastorePath
      );

      await runner.repositoryUp(parentRepoName, datastorePath, parentNetworkId);
      await runner.waitForPostgresReady(parentContainerName, parentNetworkId);
    });

    test('2. calculate parent data hash before fork', async () => {
      parentHashBeforeFork = await runner.getUsersDataHash(parentContainerName, parentNetworkId);
      expect(parentHashBeforeFork).toBeTruthy();
      // eslint-disable-next-line no-console
      console.log(`Parent hash before fork: ${parentHashBeforeFork}`);
    });

    test('3. create fork', async () => {
      await runner.repositoryDown(parentRepoName, datastorePath, parentNetworkId);
      await runner.repositoryUnmount(parentRepoName, datastorePath);

      await runner.createRepositoryFork(parentRepoName, forkRepoName, datastorePath);
      await runner.repositoryMount(forkRepoName, TEST_PASSWORD, datastorePath);

      const dockerComposeContent = runner
        .readFixture('bridge/docker-compose.postgresql.yaml')
        .replaceAll('${CONTAINER_NAME}', forkContainerName);
      await runner.writeFileToRepository(
        forkRepoName,
        'docker-compose.yaml',
        dockerComposeContent,
        datastorePath
      );

      await runner.repositoryUp(forkRepoName, datastorePath, forkNetworkId);
      await runner.waitForPostgresReady(forkContainerName, forkNetworkId);
    });

    test('4. verify fork hash matches parent hash before modifications', async () => {
      const forkHash = await runner.getUsersDataHash(forkContainerName, forkNetworkId);
      // eslint-disable-next-line no-console
      console.log(`Fork hash: ${forkHash}`);
      expect(forkHash).toBe(parentHashBeforeFork);
    });

    test('5. modify fork and verify hash differs', async () => {
      await runner.insertUserRecord(
        forkContainerName,
        'integrity_test',
        'integrity-check',
        forkNetworkId
      );

      const forkHashAfter = await runner.getUsersDataHash(forkContainerName, forkNetworkId);
      // eslint-disable-next-line no-console
      console.log(`Fork hash after modification: ${forkHashAfter}`);
      expect(forkHashAfter).not.toBe(parentHashBeforeFork);
    });

    test('6. cleanup', async () => {
      await runner.repositoryDown(forkRepoName, datastorePath, forkNetworkId);
      await runner.repositoryUnmount(forkRepoName, datastorePath);
      await runner.repositoryRm(forkRepoName, datastorePath);

      await runner.repositoryRm(parentRepoName, datastorePath);
    });
  });

// ===========================================================================
// Scenario 7: Large Data Volume Test
// ===========================================================================

test.describe
  .serial('Large Data Volume Fork @bridge @integration', () => {
    let runner: BridgeTestRunner;
    const timestamp = Date.now();
    const parentRepoName = `postgres-bulk-parent-${timestamp}`;
    const forkRepoName = `postgres-bulk-fork-${timestamp}`;
    const parentContainerName = `postgres-bulk-parent-${timestamp}`;
    const forkContainerName = `postgres-bulk-fork-${timestamp}`;
    const datastorePath = DEFAULT_DATASTORE_PATH;
    const parentNetworkId = DEFAULT_NETWORK_ID;
    const forkNetworkId = FORK_NETWORK_ID_A;

    const BULK_RECORD_COUNT = 500; // Reduced for faster testing, still validates the concept

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();
      await runner.datastoreInit('10G', datastorePath, true);
      // Setup and start daemons for both network IDs (parent and fork)
      for (const netId of [parentNetworkId, forkNetworkId]) {
        const setupResult = await runner.daemonSetup(netId);
        if (!runner.isSuccess(setupResult)) {
          throw new Error(
            `daemon_setup failed for ${netId}: ${runner.getCombinedOutput(setupResult)}`
          );
        }
        const startResult = await runner.daemonStart(undefined, undefined, netId);
        if (!runner.isSuccess(startResult)) {
          throw new Error(
            `daemon_start failed for ${netId}: ${runner.getCombinedOutput(startResult)}`
          );
        }
      }
    });

    test.afterAll(async () => {
      await runner.daemonTeardown(forkNetworkId);
      await runner.daemonTeardown(parentNetworkId);
    });

    test('1. create parent with PostgreSQL', async () => {
      await runner.repositoryNew(parentRepoName, '2G', TEST_PASSWORD, datastorePath);

      const rediaccfileContent = runner.readFixture('bridge/Rediaccfile.postgresql');
      await runner.writeFileToRepository(
        parentRepoName,
        'Rediaccfile',
        rediaccfileContent,
        datastorePath
      );

      const dockerComposeContent = runner
        .readFixture('bridge/docker-compose.postgresql.yaml')
        .replaceAll('${CONTAINER_NAME}', parentContainerName);
      await runner.writeFileToRepository(
        parentRepoName,
        'docker-compose.yaml',
        dockerComposeContent,
        datastorePath
      );

      const initSqlContent = runner.readFixture('bridge/init-postgres.sql');
      await runner.writeFileToRepository(
        parentRepoName,
        'init-postgres.sql',
        initSqlContent,
        datastorePath
      );

      await runner.repositoryUp(parentRepoName, datastorePath, parentNetworkId);
      await runner.waitForPostgresReady(parentContainerName, parentNetworkId);
    });

    test(`2. insert ${BULK_RECORD_COUNT} records into parent`, async () => {
      await runner.insertBulkUserRecords(
        parentContainerName,
        BULK_RECORD_COUNT,
        'bulk-parent',
        parentNetworkId
      );

      const count = await runner.getUserRecordCount(parentContainerName, parentNetworkId);
      expect(count).toBe(3 + BULK_RECORD_COUNT); // 3 seed + bulk
    });

    test('3. create fork with all data', async () => {
      await runner.repositoryDown(parentRepoName, datastorePath, parentNetworkId);
      await runner.repositoryUnmount(parentRepoName, datastorePath);

      await runner.createRepositoryFork(parentRepoName, forkRepoName, datastorePath);
      await runner.repositoryMount(forkRepoName, TEST_PASSWORD, datastorePath);

      const dockerComposeContent = runner
        .readFixture('bridge/docker-compose.postgresql.yaml')
        .replaceAll('${CONTAINER_NAME}', forkContainerName);
      await runner.writeFileToRepository(
        forkRepoName,
        'docker-compose.yaml',
        dockerComposeContent,
        datastorePath
      );

      await runner.repositoryUp(forkRepoName, datastorePath, forkNetworkId);
      await runner.waitForPostgresReady(forkContainerName, forkNetworkId);
    });

    test('4. verify fork has all parent records', async () => {
      const forkCount = await runner.getUserRecordCount(forkContainerName, forkNetworkId);
      expect(forkCount).toBe(3 + BULK_RECORD_COUNT);
    });

    test('5. insert additional records into fork', async () => {
      const additionalCount = 100;
      await runner.insertBulkUserRecords(
        forkContainerName,
        additionalCount,
        'bulk-fork',
        forkNetworkId
      );

      const forkCount = await runner.getUserRecordCount(forkContainerName, forkNetworkId);
      expect(forkCount).toBe(3 + BULK_RECORD_COUNT + additionalCount);
    });

    test('6. verify parent still has original count', async () => {
      await runner.repositoryMount(parentRepoName, TEST_PASSWORD, datastorePath);
      await runner.repositoryUp(parentRepoName, datastorePath, parentNetworkId);
      await runner.waitForPostgresReady(parentContainerName, parentNetworkId);

      const parentCount = await runner.getUserRecordCount(parentContainerName, parentNetworkId);
      expect(parentCount).toBe(3 + BULK_RECORD_COUNT);
    });

    test('7. cleanup', async () => {
      await runner.repositoryDown(forkRepoName, datastorePath, forkNetworkId);
      await runner.repositoryUnmount(forkRepoName, datastorePath);
      await runner.repositoryRm(forkRepoName, datastorePath);

      await runner.repositoryDown(parentRepoName, datastorePath, parentNetworkId);
      await runner.repositoryUnmount(parentRepoName, datastorePath);
      await runner.repositoryRm(parentRepoName, datastorePath);
    });
  });

// ===========================================================================
// Scenario 8: Service Restart Persistence
// ===========================================================================

test.describe
  .serial('Service Restart Persistence @bridge @integration', () => {
    let runner: BridgeTestRunner;
    const repositoryName = `postgres-restart-${Date.now()}`;
    const containerName = `postgres-restart-${Date.now()}`;
    const datastorePath = DEFAULT_DATASTORE_PATH;
    const networkId = DEFAULT_NETWORK_ID;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();
      await runner.datastoreInit('10G', datastorePath, true);
      // Setup and start daemon for Docker operations
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

    test('1. create repository with PostgreSQL', async () => {
      await runner.repositoryNew(repositoryName, '2G', TEST_PASSWORD, datastorePath);

      const rediaccfileContent = runner.readFixture('bridge/Rediaccfile.postgresql');
      await runner.writeFileToRepository(
        repositoryName,
        'Rediaccfile',
        rediaccfileContent,
        datastorePath
      );

      const dockerComposeContent = runner
        .readFixture('bridge/docker-compose.postgresql.yaml')
        .replaceAll('${CONTAINER_NAME}', containerName);
      await runner.writeFileToRepository(
        repositoryName,
        'docker-compose.yaml',
        dockerComposeContent,
        datastorePath
      );

      const initSqlContent = runner.readFixture('bridge/init-postgres.sql');
      await runner.writeFileToRepository(
        repositoryName,
        'init-postgres.sql',
        initSqlContent,
        datastorePath
      );

      await runner.repositoryUp(repositoryName, datastorePath, networkId);
      await runner.waitForPostgresReady(containerName, networkId);

      // Small delay to ensure PostgreSQL is fully operational after init scripts
      await new Promise((resolve) => setTimeout(resolve, 2000));

      // Verify seed data and insert initial record in same test to avoid race condition
      const seedCount = await runner.getUserRecordCount(containerName, networkId);
      expect(seedCount).toBe(3); // seed data

      await runner.insertUserRecord(containerName, 'restart_user_1', 'restart-cycle-1', networkId);
      const count = await runner.getUserRecordCount(containerName, networkId);
      expect(count).toBe(4); // 3 seed + 1
    });

    test('2. restart cycle 1: down and up (repository stays mounted)', async () => {
      await runner.repositoryDown(repositoryName, datastorePath, networkId);
      await runner.repositoryUp(repositoryName, datastorePath, networkId);
      await runner.waitForPostgresReady(containerName, networkId);

      const count = await runner.getUserRecordCount(containerName, networkId);
      expect(count).toBe(4);

      // Add another record
      await runner.insertUserRecord(containerName, 'restart_user_2', 'restart-cycle-2', networkId);
      const newCount = await runner.getUserRecordCount(containerName, networkId);
      expect(newCount).toBe(5);
    });

    test('3. restart cycle 2: verify persistence', async () => {
      await runner.repositoryDown(repositoryName, datastorePath, networkId);
      await runner.repositoryUp(repositoryName, datastorePath, networkId);
      await runner.waitForPostgresReady(containerName, networkId);

      // Should have all 5 records
      const count = await runner.getUserRecordCount(containerName, networkId);
      expect(count).toBe(5);

      // Verify specific records exist
      expect(await runner.recordExistsByOrigin(containerName, 'seed', networkId)).toBe(true);
      expect(await runner.recordExistsByOrigin(containerName, 'restart-cycle-1', networkId)).toBe(
        true
      );
      expect(await runner.recordExistsByOrigin(containerName, 'restart-cycle-2', networkId)).toBe(
        true
      );
    });

    test('4. restart cycle 3: final verification', async () => {
      await runner.insertUserRecord(containerName, 'restart_user_3', 'restart-cycle-3', networkId);

      await runner.repositoryDown(repositoryName, datastorePath, networkId);
      await runner.repositoryUp(repositoryName, datastorePath, networkId);
      await runner.waitForPostgresReady(containerName, networkId);

      // Should have all 6 records
      const count = await runner.getUserRecordCount(containerName, networkId);
      expect(count).toBe(6);
    });

    test('5. cleanup', async () => {
      await runner.repositoryDown(repositoryName, datastorePath, networkId);
      await runner.repositoryUnmount(repositoryName, datastorePath);
      await runner.repositoryRm(repositoryName, datastorePath);
    });
  });
