import { expect, test } from '@playwright/test';
import { DEFAULT_DATASTORE_PATH, DEFAULT_NETWORK_ID, TEST_PASSWORD } from '../src/constants';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

/**
 * Repository Prep-Only Option Tests
 *
 * Tests the prep-only option for repository_up command.
 * This option prepares the repository without starting services.
 *
 * This is part of the vault parameter fixes that ensure the
 * 'option' parameter is properly passed from vault to CLI.
 */
test.describe
  .serial('Repository Prep-Only @bridge @repository', () => {
    let runner: BridgeTestRunner;
    const repositoryName = `prep-only-test-${Date.now()}`;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();

      // Initialize datastore (LEVEL 2 prerequisite)
      const initResult = await runner.datastoreInit('10G', DEFAULT_DATASTORE_PATH, true);
      if (!runner.isSuccess(initResult)) {
        console.error('[Setup] Datastore init failed:', runner.getCombinedOutput(initResult));
      }
    });

    test('create repository for prep-only test', async () => {
      const result = await runner.repositoryNew(
        repositoryName,
        '1G',
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository_up with prep-only should not have syntax errors', async () => {
      // Unmount first (create leaves it mounted)
      await runner.repositoryUnmount(repositoryName, DEFAULT_DATASTORE_PATH);

      const result = await runner.repositoryUpPrepOnly(
        repositoryName,
        DEFAULT_DATASTORE_PATH,
        DEFAULT_NETWORK_ID
      );
      expect(runner.hasValidCommandSyntax(result)).toBe(true);
    });

    test('repository_up with prep-only should succeed', async () => {
      const result = await runner.repositoryUpPrepOnly(
        repositoryName,
        DEFAULT_DATASTORE_PATH,
        DEFAULT_NETWORK_ID
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('cleanup: delete repository', async () => {
      await runner.repositoryUnmount(repositoryName, DEFAULT_DATASTORE_PATH);
      const result = await runner.repositoryRm(repositoryName, DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Repository Prep-Only vs Full Up Comparison
 *
 * Tests that prep-only mode behaves differently from full up mode.
 */
test.describe
  .serial('Repository Prep-Only vs Full Up @bridge @repository', () => {
    let runner: BridgeTestRunner;
    const repositoryName = `prep-compare-${Date.now()}`;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();

      // Initialize datastore (LEVEL 2 prerequisite)
      await runner.datastoreInit('10G', DEFAULT_DATASTORE_PATH, true);
    });

    test('create repository for comparison', async () => {
      const result = await runner.repositoryNew(
        repositoryName,
        '1G',
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository_up (full) should succeed', async () => {
      // Unmount first (create leaves it mounted)
      await runner.repositoryUnmount(repositoryName, DEFAULT_DATASTORE_PATH);

      const result = await runner.repositoryUp(
        repositoryName,
        DEFAULT_DATASTORE_PATH,
        DEFAULT_NETWORK_ID
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository_down after full up', async () => {
      const result = await runner.repositoryDown(
        repositoryName,
        DEFAULT_DATASTORE_PATH,
        DEFAULT_NETWORK_ID
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository_up with prep-only after down should succeed', async () => {
      const result = await runner.repositoryUpPrepOnly(
        repositoryName,
        DEFAULT_DATASTORE_PATH,
        DEFAULT_NETWORK_ID
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('cleanup: unmount and delete repository', async () => {
      await runner.repositoryUnmount(repositoryName, DEFAULT_DATASTORE_PATH);
      const result = await runner.repositoryRm(repositoryName, DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });
