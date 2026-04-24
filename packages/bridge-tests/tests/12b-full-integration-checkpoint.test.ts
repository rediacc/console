import { expect, test } from '@playwright/test';
import { DEFAULT_DATASTORE_PATH, DEFAULT_NETWORK_ID, TEST_PASSWORD } from '../src/constants';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

/**
 * Checkpoint Workflow
 *
 * Tests creating checkpoints, making changes, and restoring.
 * Note: checkpoint_list and checkpoint_delete are not implemented in Go.
 */
test.describe
  .serial('Checkpoint Workflow @bridge @integration', () => {
    let runner: BridgeTestRunner;
    const repositoryName = `checkpoint-workflow-${Date.now()}`;
    const checkpoint1 = 'initial-state';
    const checkpoint2 = 'after-changes';
    const datastorePath = DEFAULT_DATASTORE_PATH;
    let criuAvailable = false;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      // Check if CRIU is available - checkpoint tests require it
      const criuCheck = await runner.checkCriu();
      criuAvailable = runner.isSuccess(criuCheck);
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

    // Setup
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

    // Daemon setup - required for checkpoint operations (creates Docker socket)
    test('2a. daemon_setup: set up daemon service', async () => {
      if (!criuAvailable) {
        test.skip();
        return;
      }
      const result = await runner.daemonSetup(DEFAULT_NETWORK_ID.toString());
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('2b. daemon_start: start daemon service', async () => {
      if (!criuAvailable) {
        test.skip();
        return;
      }
      const result = await runner.daemonStart(
        repositoryName,
        datastorePath,
        DEFAULT_NETWORK_ID.toString()
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Checkpoint workflow - requires CRIU
    test('3. create initial checkpoint', async () => {
      if (!criuAvailable) {
        test.skip();
        return;
      }
      const result = await runner.checkpointCreate(
        repositoryName,
        checkpoint1,
        datastorePath,
        DEFAULT_NETWORK_ID
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('4. start services (make changes)', async () => {
      if (!criuAvailable) {
        test.skip();
        return;
      }
      const result = await runner.repositoryUp(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('5. create checkpoint after changes', async () => {
      if (!criuAvailable) {
        test.skip();
        return;
      }
      const result = await runner.checkpointCreate(
        repositoryName,
        checkpoint2,
        datastorePath,
        DEFAULT_NETWORK_ID
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('6. stop services', async () => {
      if (!criuAvailable) {
        test.skip();
        return;
      }
      const result = await runner.repositoryDown(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('7. restore to initial checkpoint', async () => {
      if (!criuAvailable) {
        test.skip();
        return;
      }
      const result = await runner.checkpointRestore(
        repositoryName,
        checkpoint1,
        datastorePath,
        DEFAULT_NETWORK_ID
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Cleanup - always run even if CRIU tests were skipped
    test('8. unmount repository', async () => {
      const result = await runner.repositoryUnmount(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('9. delete repository', async () => {
      const result = await runner.repositoryRm(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });
