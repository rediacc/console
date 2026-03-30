import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { ErrorPatterns, expectError, nonExistentName } from '../../src/utils/errors';

/**
 * Negative test cases for region commands.
 */
test.describe('Region Error Scenarios @cli @errors', () => {
  let runner: CliTestRunner;

  test.beforeAll(() => {
    runner = CliTestRunner.fromGlobalState();
  });

  test.describe('CreateRegion errors', () => {
    test('should fail when creating region with duplicate name', async () => {
      const regionName = `error-test-dup-${Date.now()}`;

      // Create the region first
      const createResult = await runner.run(['region', 'create', '--name', regionName]);
      expect(createResult.success, `Setup failed: ${runner.getErrorMessage(createResult)}`).toBe(
        true
      );

      try {
        // Try to create with same name - should fail
        const duplicateResult = await runner.run(['region', 'create', '--name', regionName]);
        expectError(runner, duplicateResult, {
          messageContains: ErrorPatterns.REGION_ALREADY_EXISTS,
        });
      } finally {
        // Cleanup
        await runner.run(['region', 'delete', '--name', regionName, '--force']);
      }
    });
  });

  test.describe('DeleteRegion errors', () => {
    test('should fail when deleting non-existent region', async () => {
      const result = await runner.run([
        'region',
        'delete',
        '--name',
        nonExistentName('region'),
        '--force',
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.REGION_NOT_FOUND });
    });

    test('should fail when deleting Default Region (system entity)', async () => {
      const result = await runner.run(['region', 'delete', '--name', 'Default Region', '--force']);
      expectError(runner, result, { messageContains: ErrorPatterns.REGION_CANNOT_DELETE_DEFAULT });
    });
  });

  test.describe('RenameRegion errors', () => {
    test('should fail when renaming non-existent region', async () => {
      const result = await runner.run([
        'region',
        'rename',
        '--current-name',
        nonExistentName('region'),
        '--new-name',
        'new-name',
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.REGION_NOT_FOUND });
    });

    test('should fail when renaming Default Region (system entity)', async () => {
      const result = await runner.run([
        'region',
        'rename',
        '--current-name',
        'Default Region',
        '--new-name',
        'New Name',
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.REGION_CANNOT_RENAME_DEFAULT });
    });

    test('should fail when renaming to an existing region name', async () => {
      const tempRegionName = `error-test-rename-${Date.now()}`;

      // Create a temp region
      const createResult = await runner.run(['region', 'create', '--name', tempRegionName]);
      expect(createResult.success, `Setup failed: ${runner.getErrorMessage(createResult)}`).toBe(
        true
      );

      try {
        // Try to rename temp region to "Default Region" (which exists)
        const renameResult = await runner.run([
          'region',
          'rename',
          '--current-name',
          tempRegionName,
          '--new-name',
          'Default Region',
        ]);
        expectError(runner, renameResult, { messageContains: ErrorPatterns.REGION_ALREADY_EXISTS });
      } finally {
        // Cleanup
        await runner.run(['region', 'delete', '--name', tempRegionName, '--force']);
      }
    });
  });
});
