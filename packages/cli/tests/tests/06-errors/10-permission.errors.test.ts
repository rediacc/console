import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { ErrorPatterns, expectError, nonExistentName } from '../../src/utils/errors';

/**
 * Negative test cases for permission commands.
 */
test.describe('Permission Error Scenarios @cli @errors', () => {
  let runner: CliTestRunner;

  test.beforeAll(() => {
    runner = CliTestRunner.fromGlobalState();
  });

  test.describe('CreatePermissionGroup errors', () => {
    test('should fail when creating custom group in Community edition', async () => {
      const groupName = `error-test-custom-${Date.now()}`;

      // Try to create a custom permission group - may fail in Community edition
      const result = await runner.run(['permission', 'group', 'create', groupName]);

      // This test expects Community edition restriction
      // If this fails with a different error, it means we're on a paid plan
      if (!result.success) {
        expectError(runner, result, {
          messageContains: ErrorPatterns.PERMISSION_GROUP_COMMUNITY_RESTRICTION,
        });
      } else {
        // We're on a paid plan, clean up the created group
        await runner.run(['permission', 'group', 'delete', groupName, '--force']);
        console.warn('Note: Test skipped - running on paid plan, not Community edition');
      }
    });

    test('should fail when creating group with duplicate name', async () => {
      const groupName = `error-test-dup-${Date.now()}`;

      // Create the group first (if Community edition, skip this test)
      const createResult = await runner.run(['permission', 'group', 'create', groupName]);

      if (!createResult.success) {
        // Community edition - can't test duplicate scenario
        console.warn('Note: Test skipped - Community edition restriction');
        return;
      }

      try {
        // Try to create with same name - should fail
        const duplicateResult = await runner.run(['permission', 'group', 'create', groupName]);
        expectError(runner, duplicateResult, {
          messageContains: ErrorPatterns.PERMISSION_GROUP_ALREADY_EXISTS,
        });
      } finally {
        // Cleanup
        await runner.run(['permission', 'group', 'delete', groupName, '--force']);
      }
    });
  });

  test.describe('DeletePermissionGroup errors', () => {
    test('should fail when deleting non-existent permission group', async () => {
      const result = await runner.run([
        'permission',
        'group',
        'delete',
        nonExistentName('permgroup'),
        '--force',
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.PERMISSION_GROUP_NOT_FOUND });
    });

    test('should fail when deleting system group (Administrators)', async () => {
      const result = await runner.run([
        'permission',
        'group',
        'delete',
        'Administrators',
        '--force',
      ]);

      // System groups can fail deletion for two reasons:
      // 1. They're in use by users (checked first in stored procedure)
      // 2. They're protected system groups
      // We just verify that deletion is blocked
      expect(result.success, 'Should fail when deleting system group').toBe(false);
      const errorMsg = runner.getErrorMessage(result).toLowerCase();
      const isSystemGroupError = errorMsg.includes('system group') || errorMsg.includes('in use');
      expect(isSystemGroupError, 'Should indicate system group or in-use error').toBe(true);
    });

    test('should fail when deleting system group (Users)', async () => {
      const result = await runner.run(['permission', 'group', 'delete', 'Users', '--force']);

      expect(result.success, 'Should fail when deleting system group').toBe(false);
      const errorMsg = runner.getErrorMessage(result).toLowerCase();
      const isSystemGroupError = errorMsg.includes('system group') || errorMsg.includes('in use');
      expect(isSystemGroupError, 'Should indicate system group or in-use error').toBe(true);
    });

    test('should fail when deleting system group (Bridges)', async () => {
      const result = await runner.run(['permission', 'group', 'delete', 'Bridges', '--force']);

      expect(result.success, 'Should fail when deleting system group').toBe(false);
      const errorMsg = runner.getErrorMessage(result).toLowerCase();
      const isSystemGroupError = errorMsg.includes('system group') || errorMsg.includes('in use');
      expect(isSystemGroupError, 'Should indicate system group or in-use error').toBe(true);
    });
  });

  test.describe('GetPermissionGroupDetails errors', () => {
    test('should fail when showing non-existent permission group', async () => {
      const result = await runner.run([
        'permission',
        'group',
        'show',
        nonExistentName('permgroup'),
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.PERMISSION_GROUP_NOT_FOUND });
    });
  });

  test.describe('CreatePermissionInGroup errors', () => {
    test('should fail when adding permission to non-existent group', async () => {
      const result = await runner.run([
        'permission',
        'add',
        nonExistentName('permgroup'),
        'TEAM_CREATE',
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.PERMISSION_GROUP_NOT_FOUND });
    });

    test('should fail when adding permission to system group (Administrators)', async () => {
      const result = await runner.run(['permission', 'add', 'Administrators', 'TEAM_CREATE']);
      expectError(runner, result, {
        messageContains: ErrorPatterns.PERMISSION_CANNOT_MODIFY_SYSTEM,
      });
    });

    test('should fail when adding permission to system group (Bridges)', async () => {
      const result = await runner.run(['permission', 'add', 'Bridges', 'TEAM_CREATE']);
      expectError(runner, result, {
        messageContains: ErrorPatterns.PERMISSION_CANNOT_MODIFY_SYSTEM,
      });
    });

    test('should fail when adding invalid permission name', async () => {
      // First, try to create a custom group (will skip if Community edition)
      const groupName = `error-test-perm-${Date.now()}`;
      const createResult = await runner.run(['permission', 'group', 'create', groupName]);

      if (!createResult.success) {
        console.warn('Note: Test skipped - Community edition restriction');
        return;
      }

      try {
        const result = await runner.run([
          'permission',
          'add',
          groupName,
          'INVALID_PERMISSION_NAME',
        ]);
        expectError(runner, result, { messageContains: ErrorPatterns.PERMISSION_INVALID_NAME });
      } finally {
        // Cleanup
        await runner.run(['permission', 'group', 'delete', groupName, '--force']);
      }
    });
  });

  test.describe('DeletePermissionFromGroup errors', () => {
    test('should fail when removing permission from non-existent group', async () => {
      const result = await runner.run([
        'permission',
        'remove',
        nonExistentName('permgroup'),
        'TEAM_CREATE',
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.PERMISSION_GROUP_NOT_FOUND });
    });

    test('should fail when removing permission from system group (Administrators)', async () => {
      const result = await runner.run(['permission', 'remove', 'Administrators', 'TEAM_CREATE']);
      expectError(runner, result, {
        messageContains: ErrorPatterns.PERMISSION_CANNOT_MODIFY_SYSTEM,
      });
    });

    test('should fail when removing permission from system group (Bridges)', async () => {
      const result = await runner.run(['permission', 'remove', 'Bridges', 'TEAM_CREATE']);
      expectError(runner, result, {
        messageContains: ErrorPatterns.PERMISSION_CANNOT_MODIFY_SYSTEM,
      });
    });
  });
});
