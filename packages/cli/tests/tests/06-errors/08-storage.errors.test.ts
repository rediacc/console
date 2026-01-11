import { expect, test } from '@playwright/test';
import { SYSTEM_DEFAULTS } from '@rediacc/shared/config';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { ErrorPatterns, expectError, nonExistentName } from '../../src/utils/errors';

/**
 * Negative test cases for storage commands.
 */
test.describe('Storage Error Scenarios @cli @errors', () => {
  let runner: CliTestRunner;
  let defaultTeamName: string;

  test.beforeAll(async () => {
    runner = CliTestRunner.fromGlobalState();

    // Get default team for tests
    const teamsResult = await runner.teamList();
    const teams = runner.expectSuccessArray<{ teamName: string }>(teamsResult);
    defaultTeamName =
      teams.find((t) => t.teamName !== 'Private Team')?.teamName ?? SYSTEM_DEFAULTS.TEAM_NAME;
  });

  test.describe('CreateStorage errors', () => {
    test('should fail when creating storage with non-existent team', async () => {
      const result = await runner.run([
        'storage',
        'create',
        'test-storage',
        '--team',
        nonExistentName('team'),
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });

    test('should fail when creating storage with duplicate name', async () => {
      const storageName = `error-test-dup-${Date.now()}`;

      // Create the storage first
      const createResult = await runner.run([
        'storage',
        'create',
        storageName,
        '--team',
        defaultTeamName,
      ]);
      expect(createResult.success, `Setup failed: ${runner.getErrorMessage(createResult)}`).toBe(
        true
      );

      // Verify storage exists before trying duplicate creation
      const listResult = await runner.run(['storage', 'list', '--team', defaultTeamName]);
      const storageList = runner.expectSuccessArray<{ storageName: string }>(listResult);
      const exists = storageList.some((s) => s.storageName === storageName);
      expect(exists, `Storage ${storageName} not found in list after creation`).toBe(true);

      try {
        // Try to create with same name - should fail
        const duplicateResult = await runner.run([
          'storage',
          'create',
          storageName,
          '--team',
          defaultTeamName,
        ]);
        expectError(runner, duplicateResult, {
          messageContains: ErrorPatterns.STORAGE_ALREADY_EXISTS,
        });
      } finally {
        // Cleanup
        await runner.run(['storage', 'delete', storageName, '--team', defaultTeamName, '--force']);
      }
    });
  });

  test.describe('DeleteStorage errors', () => {
    test('should fail when deleting non-existent storage', async () => {
      const result = await runner.run([
        'storage',
        'delete',
        nonExistentName('storage'),
        '--team',
        defaultTeamName,
        '--force',
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.STORAGE_NOT_FOUND });
    });

    test('should fail when deleting storage from non-existent team', async () => {
      const result = await runner.run([
        'storage',
        'delete',
        'some-storage',
        '--team',
        nonExistentName('team'),
        '--force',
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });
  });

  test.describe('RenameStorage errors', () => {
    test('should fail when renaming non-existent storage', async () => {
      const result = await runner.run([
        'storage',
        'rename',
        nonExistentName('storage'),
        'new-name',
        '--team',
        defaultTeamName,
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.STORAGE_NOT_FOUND });
    });

    test('should fail when renaming storage from non-existent team', async () => {
      const result = await runner.run([
        'storage',
        'rename',
        'some-storage',
        'new-name',
        '--team',
        nonExistentName('team'),
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });

    test('should fail when renaming to an existing storage name', async () => {
      const storageName1 = `error-test-rename-1-${Date.now()}`;
      const storageName2 = `error-test-rename-2-${Date.now()}`;

      // Create two storage systems
      const createResult1 = await runner.run([
        'storage',
        'create',
        storageName1,
        '--team',
        defaultTeamName,
      ]);
      expect(createResult1.success, `Setup failed: ${runner.getErrorMessage(createResult1)}`).toBe(
        true
      );

      const createResult2 = await runner.run([
        'storage',
        'create',
        storageName2,
        '--team',
        defaultTeamName,
      ]);
      expect(createResult2.success, `Setup failed: ${runner.getErrorMessage(createResult2)}`).toBe(
        true
      );

      let renameResult;
      try {
        // Try to rename storageName1 to storageName2 (which already exists) - should fail
        renameResult = await runner.run([
          'storage',
          'rename',
          storageName1,
          storageName2,
          '--team',
          defaultTeamName,
        ]);
        expectError(runner, renameResult, {
          messageContains: ErrorPatterns.STORAGE_ALREADY_EXISTS,
        });
      } finally {
        // Cleanup both storage systems (use the original name for storageName1 if rename failed)
        if (!renameResult?.success) {
          await runner.run([
            'storage',
            'delete',
            storageName1,
            '--team',
            defaultTeamName,
            '--force',
          ]);
        }
        await runner.run(['storage', 'delete', storageName2, '--team', defaultTeamName, '--force']);
      }
    });

    test('should fail when renaming to an empty name', async () => {
      const storageName = `error-test-empty-${Date.now()}`;

      // Create a storage first
      const createResult = await runner.run([
        'storage',
        'create',
        storageName,
        '--team',
        defaultTeamName,
      ]);
      expect(createResult.success, `Setup failed: ${runner.getErrorMessage(createResult)}`).toBe(
        true
      );

      try {
        // Try to rename to empty string - should fail
        const renameResult = await runner.run([
          'storage',
          'rename',
          storageName,
          '',
          '--team',
          defaultTeamName,
        ]);
        expectError(runner, renameResult, { messageContains: ErrorPatterns.STORAGE_NAME_EMPTY });
      } finally {
        // Cleanup
        await runner.run(['storage', 'delete', storageName, '--team', defaultTeamName, '--force']);
      }
    });
  });

  test.describe('Storage list errors', () => {
    test('should return empty list for non-existent team', async () => {
      const result = await runner.run(['storage', 'list', '--team', nonExistentName('team')]);
      // Note: API returns success with empty array for non-existent team
      expect(result.success).toBe(true);
      expect(result.json).toEqual([]);
    });
  });
});
