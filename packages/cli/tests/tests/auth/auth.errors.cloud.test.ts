import { test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { ErrorPatterns, expectError } from '../../src/utils/errors';

/**
 * Negative test cases for auth commands.
 */
test.describe('Auth Error Scenarios @cli @errors', () => {
  let runner: CliTestRunner;

  test.beforeAll(() => {
    runner = CliTestRunner.fromGlobalState();
  });

  test.describe('Token revoke errors', () => {
    test('should fail when revoking non-existent token', async () => {
      // Request ID must be numeric (INT in SQL) - use a large number unlikely to exist
      const fakeRequestId = '999999999';
      const result = await runner.run(['auth', 'token', 'revoke', fakeRequestId]);

      // API should return "Target session not found or already terminated"
      expectError(runner, result, { messageContains: ErrorPatterns.QUEUE_NOT_FOUND });
    });
  });

  test.describe('Token fork errors', () => {
    test('should fail with token expiration below minimum (1 hour)', async () => {
      const result = await runner.run(['auth', 'token', 'fork', '-n', 'test-token', '-e', '0']);
      expectError(runner, result, { messageContains: ErrorPatterns.TOKEN_EXPIRATION_INVALID });
    });

    test('should fail with token expiration above maximum (720 hours)', async () => {
      const result = await runner.run(['auth', 'token', 'fork', '-n', 'test-token', '-e', '1000']);
      expectError(runner, result, { messageContains: ErrorPatterns.TOKEN_EXPIRATION_INVALID });
    });
  });
});
