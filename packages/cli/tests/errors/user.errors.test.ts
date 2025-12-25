import { describe, it, beforeAll } from 'vitest';
import { runCli } from '../helpers/cli.js';
import { expectError, nonExistentName, ErrorPatterns } from '../helpers/errors.js';
import { getConfig } from '../helpers/config.js';

/**
 * Negative test cases for user commands.
 * Tests backend error responses from middleware stored procedures.
 */
describe('user error scenarios', () => {
  let currentUserEmail: string;

  beforeAll(async () => {
    // Get current user email for self-deactivation test
    const config = getConfig();
    currentUserEmail = config.email;
  });

  // ============================================
  // User Deactivate Errors
  // ============================================
  describe('User deactivate errors', () => {
    it('should fail when deactivating non-existent user', async () => {
      const result = await runCli([
        'user',
        'deactivate',
        `${nonExistentName('user')}@example.com`,
        '--force',
      ]);
      expectError(result, { messageContains: ErrorPatterns.USER_EMAIL_NOT_FOUND });
    });

    it('should fail when deactivating your own account', async () => {
      const result = await runCli(['user', 'deactivate', currentUserEmail, '--force']);
      expectError(result, { messageContains: ErrorPatterns.USER_CANNOT_DEACTIVATE_SELF });
    });
  });

  // ============================================
  // User Reactivate Errors
  // ============================================
  describe('User reactivate errors', () => {
    it('should fail when reactivating non-existent user', async () => {
      const result = await runCli(['user', 'reactivate', `${nonExistentName('user')}@example.com`]);
      expectError(result, { messageContains: ErrorPatterns.USER_EMAIL_NOT_FOUND });
    });

    // Note: Testing "user already activated" error requires a deactivated user,
    // which we cannot create with current user (can't deactivate self).
    // This would require multi-user setup which is beyond the scope of simple error tests.
  });

  // ============================================
  // User Permission Assign Errors
  // ============================================
  describe('User permission assign errors', () => {
    it('should fail when assigning permissions to non-existent user', async () => {
      const result = await runCli([
        'user',
        'permission',
        'assign',
        `${nonExistentName('user')}@example.com`,
        'Users',
      ]);
      expectError(result, { messageContains: ErrorPatterns.USER_EMAIL_NOT_FOUND });
    });

    it('should fail when assigning non-existent permission group', async () => {
      const result = await runCli([
        'user',
        'permission',
        'assign',
        currentUserEmail,
        nonExistentName('permission-group'),
      ]);
      expectError(result, { messageContains: ErrorPatterns.PERMISSION_GROUP_NOT_FOUND });
    });
  });
});
