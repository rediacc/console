import { test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { ErrorPatterns, expectError, nonExistentName } from '../../src/utils/errors';

/**
 * Negative test cases for user commands.
 */
test.describe('User Error Scenarios @cli @errors', () => {
  let runner: CliTestRunner;
  let currentUserEmail: string;

  test.beforeAll(() => {
    runner = CliTestRunner.fromGlobalState();
    currentUserEmail = runner.config.credentials!.email;
  });

  test.describe('User deactivate errors', () => {
    test('should fail when deactivating non-existent user', async () => {
      const result = await runner.run([
        'user',
        'deactivate',
        `${nonExistentName('user')}@example.com`,
        '--force',
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.USER_EMAIL_NOT_FOUND });
    });

    test('should fail when deactivating your own account', async () => {
      const result = await runner.run(['user', 'deactivate', currentUserEmail, '--force']);
      expectError(runner, result, { messageContains: ErrorPatterns.USER_CANNOT_DEACTIVATE_SELF });
    });
  });

  test.describe('User reactivate errors', () => {
    test('should fail when reactivating non-existent user', async () => {
      const result = await runner.run([
        'user',
        'reactivate',
        `${nonExistentName('user')}@example.com`,
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.USER_EMAIL_NOT_FOUND });
    });
  });

  test.describe('User permission assign errors', () => {
    test('should fail when assigning permissions to non-existent user', async () => {
      const result = await runner.run([
        'user',
        'permission',
        'assign',
        `${nonExistentName('user')}@example.com`,
        'Users',
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.USER_EMAIL_NOT_FOUND });
    });

    test('should fail when assigning non-existent permission group', async () => {
      const result = await runner.run([
        'user',
        'permission',
        'assign',
        currentUserEmail,
        nonExistentName('permission-group'),
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.PERMISSION_GROUP_NOT_FOUND });
    });
  });
});
