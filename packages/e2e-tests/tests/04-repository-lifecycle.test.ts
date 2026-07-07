import { expect, test } from '@playwright/test';
import { DEFAULT_DATASTORE_PATH, TEST_PASSWORD, TEST_REPOSITORY_NAME } from '../src/constants';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

/**
 * Repository Lifecycle Tests (12 functions)
 *
 * Tests repository management functions in proper lifecycle order.
 * These are LEVEL 3 functions - require datastore setup first.
 *
 * Functions tested:
 * - new (create repository)
 * - list
 * - info
 * - status
 * - mount
 * - validate
 * - resize / grow
 * - unmount
 * - rm (delete)
 *
 * Lifecycle order (STRICT):
 * 1. new (create)
 * 2. list (verify exists)
 * 3. mount
 * 4. validate
 * 5. resize/grow
 * 6. unmount
 * 7. rm (cleanup)
 */
test.describe
  .serial('Repository Lifecycle @bridge', () => {
    let runner: BridgeTestRunner;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();

      // Initialize and mount datastore (LEVEL 2 prerequisite for repository operations)
      const initResult = await runner.datastoreInit('10G', DEFAULT_DATASTORE_PATH, true);
      if (!runner.isSuccess(initResult)) {
        console.error('[Setup] Datastore init failed:', runner.getCombinedOutput(initResult));
      }
    });

    // ===========================================================================
    // Individual Function Syntax Tests
    // ===========================================================================

    test('repository new should not have shell syntax errors', async () => {
      const result = await runner.repositoryNew(
        TEST_REPOSITORY_NAME,
        '1G',
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository list should not have shell syntax errors', async () => {
      const result = await runner.repositoryList(DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository info should not have shell syntax errors', async () => {
      const result = await runner.repositoryInfo(TEST_REPOSITORY_NAME, DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository status should not have shell syntax errors', async () => {
      const result = await runner.repositoryStatus(TEST_REPOSITORY_NAME, DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Note: repository_create leaves repo mounted, so unmount first before testing mount
    test('repository unmount should not have shell syntax errors', async () => {
      const result = await runner.repositoryUnmount(TEST_REPOSITORY_NAME, DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository mount should not have shell syntax errors', async () => {
      const result = await runner.repositoryMount(
        TEST_REPOSITORY_NAME,
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository validate should not have shell syntax errors', async () => {
      const result = await runner.repositoryValidate(TEST_REPOSITORY_NAME, DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Note: resize/expand require unmounted repo - unmount first
    test('repository resize should not have shell syntax errors', async () => {
      await runner.repositoryUnmount(TEST_REPOSITORY_NAME, DEFAULT_DATASTORE_PATH);
      const result = await runner.repositoryResize(
        TEST_REPOSITORY_NAME,
        '2G',
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Note: expand (grow) requires mounted repo - mount first after resize
    test('repository grow should not have shell syntax errors', async () => {
      await runner.repositoryMount(TEST_REPOSITORY_NAME, TEST_PASSWORD, DEFAULT_DATASTORE_PATH);
      const result = await runner.repositoryGrow(
        TEST_REPOSITORY_NAME,
        '3G',
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository rm should not have shell syntax errors', async () => {
      await runner.repositoryUnmount(TEST_REPOSITORY_NAME, DEFAULT_DATASTORE_PATH);
      const result = await runner.repositoryRm(TEST_REPOSITORY_NAME, DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Repository with Password Tests
 *
 * Tests repository operations with encryption password.
 */
test.describe
  .serial('Repository with Password @bridge', () => {
    let runner: BridgeTestRunner;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();

      // Initialize datastore (LEVEL 2 prerequisite)
      await runner.datastoreInit('10G', DEFAULT_DATASTORE_PATH, true);
    });

    test('repository new with password should not have syntax errors', async () => {
      const result = await runner.repositoryNew(
        'encrypted-repo',
        '1G',
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Note: repository_create leaves repo mounted, unmount first
    test('repository unmount with password should work', async () => {
      const result = await runner.repositoryUnmount('encrypted-repo', DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository mount with password should not have syntax errors', async () => {
      const result = await runner.repositoryMount(
        'encrypted-repo',
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository with special characters in password should handle correctly', async () => {
      // Test with special characters that might need escaping
      const result = await runner.repositoryNew(
        'special-repo',
        '1G',
        'p@$$w0rd!#$%',
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Repository Size Operations Tests
 *
 * Tests repository size management functions.
 */
test.describe
  .serial('Repository Size Operations @bridge', () => {
    let runner: BridgeTestRunner;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();

      // Initialize datastore (LEVEL 2 prerequisite)
      await runner.datastoreInit('10G', DEFAULT_DATASTORE_PATH, true);
    });

    test('repository new with various sizes should work', async () => {
      // Create a smaller repo for subsequent resize tests
      const result = await runner.repositoryNew(
        'size-test-repo',
        '500M',
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository unmount before resize', async () => {
      const result = await runner.repositoryUnmount('size-test-repo', DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository resize to larger size should work', async () => {
      const result = await runner.repositoryResize(
        'size-test-repo',
        '1G',
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Note: expand (grow) requires mounted repo - mount first after resize
    test('repository grow should work', async () => {
      await runner.repositoryMount('size-test-repo', TEST_PASSWORD, DEFAULT_DATASTORE_PATH);
      const result = await runner.repositoryGrow(
        'size-test-repo',
        '2G',
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Repository Full Lifecycle Test
 *
 * Tests the complete repository lifecycle in strict order.
 * This validates the correct command sequence.
 */
test.describe
  .serial('Repository Full Lifecycle @bridge @lifecycle', () => {
    let runner: BridgeTestRunner;
    const repositoryName = `lifecycle-test-${Date.now()}`;
    const datastorePath = DEFAULT_DATASTORE_PATH;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      await runner.resetWorkerState();

      // Initialize datastore (LEVEL 2 prerequisite)
      await runner.datastoreInit('10G', datastorePath, true);
    });

    test('1. new: create repository', async () => {
      const result = await runner.repositoryNew(repositoryName, '1G', TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('2. list: verify repository exists', async () => {
      const result = await runner.repositoryList(datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('3. info: get repository details', async () => {
      const result = await runner.repositoryInfo(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Note: repository_create leaves repo mounted, unmount first to test mount
    test('4a. unmount: unmount for mount test', async () => {
      const result = await runner.repositoryUnmount(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('4b. mount: mount repository', async () => {
      const result = await runner.repositoryMount(repositoryName, TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('5. status: check mounted repository status', async () => {
      const result = await runner.repositoryStatus(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('6. validate: validate mounted repository', async () => {
      const result = await runner.repositoryValidate(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('7a. unmount: unmount before resize', async () => {
      const result = await runner.repositoryUnmount(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('7b. resize: resize repository', async () => {
      const result = await runner.repositoryResize(
        repositoryName,
        '2G',
        TEST_PASSWORD,
        datastorePath
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('8. unmount: unmount repository', async () => {
      const result = await runner.repositoryUnmount(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('9. rm: delete repository', async () => {
      const result = await runner.repositoryRm(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Repository Error Handling Tests
 *
 * Tests error handling for invalid operations.
 */
test.describe('Repository Error Handling @bridge', () => {
  let runner: BridgeTestRunner;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
    await runner.resetWorkerState();

    // Initialize datastore (LEVEL 2 prerequisite)
    await runner.datastoreInit('10G', DEFAULT_DATASTORE_PATH, true);
  });

  test('operations on nonexistent repository should handle gracefully', async () => {
    const nonexistent = 'nonexistent-repo-xyz';

    // These should fail but NOT have shell syntax errors
    const infoResult = await runner.repositoryInfo(nonexistent, DEFAULT_DATASTORE_PATH);
    expect(infoResult.stderr).not.toContain('syntax error');
    expect(infoResult.stderr).not.toContain('unexpected token');

    const mountResult = await runner.repositoryMount(
      nonexistent,
      TEST_PASSWORD,
      DEFAULT_DATASTORE_PATH
    );
    expect(mountResult.stderr).not.toContain('syntax error');
    expect(mountResult.stderr).not.toContain('unexpected token');
  });

  test('repository with invalid name should handle gracefully', async () => {
    // Names with spaces may be rejected, but should not cause syntax errors
    const result = await runner.repositoryNew(
      'invalid name',
      '1G',
      TEST_PASSWORD,
      DEFAULT_DATASTORE_PATH
    );
    expect(result.stderr).not.toContain('syntax error');
    expect(result.stderr).not.toContain('unexpected token');
  });

  test('repository with invalid size should handle gracefully', async () => {
    // Invalid size should be rejected, but should not cause syntax errors
    const result = await runner.repositoryNew(
      'size-test',
      'invalid',
      TEST_PASSWORD,
      DEFAULT_DATASTORE_PATH
    );
    expect(result.stderr).not.toContain('syntax error');
    expect(result.stderr).not.toContain('unexpected token');
  });
});
