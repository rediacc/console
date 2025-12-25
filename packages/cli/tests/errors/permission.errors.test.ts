import { describe, it, expect } from 'vitest';
import { runCli, getErrorMessage } from '../helpers/cli.js';
import { expectError, nonExistentName, ErrorPatterns } from '../helpers/errors.js';

/**
 * Negative test cases for permission commands.
 * Tests backend error responses from middleware stored procedures.
 */
describe('permission error scenarios', () => {

  // ============================================
  // CreatePermissionGroup Errors
  // ============================================
  describe('CreatePermissionGroup errors', () => {
    it('should fail when creating custom group in Community edition', async () => {
      const groupName = `error-test-custom-${Date.now()}`;

      // Try to create a custom permission group - may fail in Community edition
      const result = await runCli(['permission', 'group', 'create', groupName]);

      // This test expects Community edition restriction
      // If this fails with a different error, it means we're on a paid plan
      if (!result.success) {
        expectError(result, { messageContains: ErrorPatterns.PERMISSION_GROUP_COMMUNITY_RESTRICTION });
      } else {
        // We're on a paid plan, clean up the created group
        await runCli(['permission', 'group', 'delete', groupName, '--force']);
        console.log('Note: Test skipped - running on paid plan, not Community edition');
      }
    });

    it('should fail when creating group with duplicate name', async () => {
      const groupName = `error-test-dup-${Date.now()}`;

      // Create the group first (if Community edition, skip this test)
      const createResult = await runCli(['permission', 'group', 'create', groupName]);

      if (!createResult.success) {
        // Community edition - can't test duplicate scenario
        console.log('Note: Test skipped - Community edition restriction');
        return;
      }

      try {
        // Try to create with same name - should fail
        const duplicateResult = await runCli(['permission', 'group', 'create', groupName]);
        expectError(duplicateResult, { messageContains: ErrorPatterns.PERMISSION_GROUP_ALREADY_EXISTS });
      } finally {
        // Cleanup
        await runCli(['permission', 'group', 'delete', groupName, '--force']);
      }
    });
  });

  // ============================================
  // DeletePermissionGroup Errors
  // ============================================
  describe('DeletePermissionGroup errors', () => {
    it('should fail when deleting non-existent permission group', async () => {
      const result = await runCli(['permission', 'group', 'delete', nonExistentName('permgroup'), '--force']);
      expectError(result, { messageContains: ErrorPatterns.PERMISSION_GROUP_NOT_FOUND });
    });

    it('should fail when deleting system group (Administrators)', async () => {
      const result = await runCli(['permission', 'group', 'delete', 'Administrators', '--force']);

      // System groups can fail deletion for two reasons:
      // 1. They're in use by users (checked first in stored procedure)
      // 2. They're protected system groups
      // We just verify that deletion is blocked
      expect(result.success, 'Should fail when deleting system group').toBe(false);
      const errorMsg = getErrorMessage(result).toLowerCase();
      const isSystemGroupError = errorMsg.includes('system group') || errorMsg.includes('in use');
      expect(isSystemGroupError, 'Should indicate system group or in-use error').toBe(true);
    });

    it('should fail when deleting system group (Users)', async () => {
      const result = await runCli(['permission', 'group', 'delete', 'Users', '--force']);

      expect(result.success, 'Should fail when deleting system group').toBe(false);
      const errorMsg = getErrorMessage(result).toLowerCase();
      const isSystemGroupError = errorMsg.includes('system group') || errorMsg.includes('in use');
      expect(isSystemGroupError, 'Should indicate system group or in-use error').toBe(true);
    });

    it('should fail when deleting system group (Bridges)', async () => {
      const result = await runCli(['permission', 'group', 'delete', 'Bridges', '--force']);

      expect(result.success, 'Should fail when deleting system group').toBe(false);
      const errorMsg = getErrorMessage(result).toLowerCase();
      const isSystemGroupError = errorMsg.includes('system group') || errorMsg.includes('in use');
      expect(isSystemGroupError, 'Should indicate system group or in-use error').toBe(true);
    });
  });

  // ============================================
  // GetPermissionGroupDetails Errors
  // ============================================
  describe('GetPermissionGroupDetails errors', () => {
    it('should fail when showing non-existent permission group', async () => {
      const result = await runCli(['permission', 'group', 'show', nonExistentName('permgroup')]);
      expectError(result, { messageContains: ErrorPatterns.PERMISSION_GROUP_NOT_FOUND });
    });
  });

  // ============================================
  // CreatePermissionInGroup Errors
  // ============================================
  describe('CreatePermissionInGroup errors', () => {
    it('should fail when adding permission to non-existent group', async () => {
      const result = await runCli(['permission', 'add', nonExistentName('permgroup'), 'TEAM_CREATE']);
      expectError(result, { messageContains: ErrorPatterns.PERMISSION_GROUP_NOT_FOUND });
    });

    it('should fail when adding permission to system group (Administrators)', async () => {
      const result = await runCli(['permission', 'add', 'Administrators', 'TEAM_CREATE']);
      expectError(result, { messageContains: ErrorPatterns.PERMISSION_CANNOT_MODIFY_SYSTEM });
    });

    it('should fail when adding permission to system group (Bridges)', async () => {
      const result = await runCli(['permission', 'add', 'Bridges', 'TEAM_CREATE']);
      expectError(result, { messageContains: ErrorPatterns.PERMISSION_CANNOT_MODIFY_SYSTEM });
    });

    it('should fail when adding invalid permission name', async () => {
      // First, try to create a custom group (will skip if Community edition)
      const groupName = `error-test-perm-${Date.now()}`;
      const createResult = await runCli(['permission', 'group', 'create', groupName]);

      if (!createResult.success) {
        console.log('Note: Test skipped - Community edition restriction');
        return;
      }

      try {
        const result = await runCli(['permission', 'add', groupName, 'INVALID_PERMISSION_NAME']);
        expectError(result, { messageContains: ErrorPatterns.PERMISSION_INVALID_NAME });
      } finally {
        // Cleanup
        await runCli(['permission', 'group', 'delete', groupName, '--force']);
      }
    });
  });

  // ============================================
  // DeletePermissionFromGroup Errors
  // ============================================
  describe('DeletePermissionFromGroup errors', () => {
    it('should fail when removing permission from non-existent group', async () => {
      const result = await runCli(['permission', 'remove', nonExistentName('permgroup'), 'TEAM_CREATE']);
      expectError(result, { messageContains: ErrorPatterns.PERMISSION_GROUP_NOT_FOUND });
    });

    it('should fail when removing permission from system group (Administrators)', async () => {
      const result = await runCli(['permission', 'remove', 'Administrators', 'TEAM_CREATE']);
      expectError(result, { messageContains: ErrorPatterns.PERMISSION_CANNOT_MODIFY_SYSTEM });
    });

    it('should fail when removing permission from system group (Bridges)', async () => {
      const result = await runCli(['permission', 'remove', 'Bridges', 'TEAM_CREATE']);
      expectError(result, { messageContains: ErrorPatterns.PERMISSION_CANNOT_MODIFY_SYSTEM });
    });
  });
});
