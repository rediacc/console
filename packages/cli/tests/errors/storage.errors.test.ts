import { describe, it, expect, beforeAll } from 'vitest';
import { runCli, getErrorMessage } from '../helpers/cli.js';
import { expectError, nonExistentName, ErrorPatterns } from '../helpers/errors.js';

/**
 * Negative test cases for storage commands.
 * Tests backend error responses from middleware stored procedures.
 */
describe('storage error scenarios', () => {
  let defaultTeamName: string;

  beforeAll(async () => {
    // Get default team for tests
    const teamsResult = await runCli(['team', 'list']);
    const teams = teamsResult.json as { teamName: string }[];
    defaultTeamName = teams.find((t) => t.teamName !== 'Private Team')?.teamName ?? 'Private Team';
  });

  // ============================================
  // CreateStorage Errors
  // ============================================
  describe('CreateStorage errors', () => {
    it('should fail when creating storage with non-existent team', async () => {
      const result = await runCli(['storage', 'create', 'test-storage', '--team', nonExistentName('team')]);
      expectError(result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });

    it('should fail when creating storage with duplicate name', async () => {
      const storageName = `error-test-dup-${Date.now()}`;

      // Create the storage first
      const createResult = await runCli(['storage', 'create', storageName, '--team', defaultTeamName]);
      expect(createResult.success, `Setup failed: ${getErrorMessage(createResult)}`).toBe(true);

      // Verify storage exists before trying duplicate creation
      const listResult = await runCli(['storage', 'list', '--team', defaultTeamName]);
      const storageList = listResult.json as { storageName: string }[];
      const exists = storageList.some((s) => s.storageName === storageName);
      expect(exists, `Storage ${storageName} not found in list after creation`).toBe(true);

      try {
        // Try to create with same name - should fail
        const duplicateResult = await runCli(['storage', 'create', storageName, '--team', defaultTeamName]);
        expectError(duplicateResult, { messageContains: ErrorPatterns.STORAGE_ALREADY_EXISTS });
      } finally {
        // Cleanup
        await runCli(['storage', 'delete', storageName, '--team', defaultTeamName, '--force']);
      }
    });
  });

  // ============================================
  // DeleteStorage Errors
  // ============================================
  describe('DeleteStorage errors', () => {
    it('should fail when deleting non-existent storage', async () => {
      const result = await runCli(['storage', 'delete', nonExistentName('storage'), '--team', defaultTeamName, '--force']);
      expectError(result, { messageContains: ErrorPatterns.STORAGE_NOT_FOUND });
    });

    it('should fail when deleting storage from non-existent team', async () => {
      const result = await runCli(['storage', 'delete', 'some-storage', '--team', nonExistentName('team'), '--force']);
      expectError(result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });
  });

  // ============================================
  // RenameStorage (UpdateStorageName) Errors
  // ============================================
  describe('RenameStorage errors', () => {
    it('should fail when renaming non-existent storage', async () => {
      const result = await runCli(['storage', 'rename', nonExistentName('storage'), 'new-name', '--team', defaultTeamName]);
      expectError(result, { messageContains: ErrorPatterns.STORAGE_NOT_FOUND });
    });

    it('should fail when renaming storage from non-existent team', async () => {
      const result = await runCli(['storage', 'rename', 'some-storage', 'new-name', '--team', nonExistentName('team')]);
      expectError(result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });

    it('should fail when renaming to an existing storage name', async () => {
      const storageName1 = `error-test-rename-1-${Date.now()}`;
      const storageName2 = `error-test-rename-2-${Date.now()}`;

      // Create two storage systems
      const createResult1 = await runCli(['storage', 'create', storageName1, '--team', defaultTeamName]);
      expect(createResult1.success, `Setup failed: ${getErrorMessage(createResult1)}`).toBe(true);

      const createResult2 = await runCli(['storage', 'create', storageName2, '--team', defaultTeamName]);
      expect(createResult2.success, `Setup failed: ${getErrorMessage(createResult2)}`).toBe(true);

      let renameResult;
      try {
        // Try to rename storageName1 to storageName2 (which already exists) - should fail
        renameResult = await runCli(['storage', 'rename', storageName1, storageName2, '--team', defaultTeamName]);
        expectError(renameResult, { messageContains: ErrorPatterns.STORAGE_ALREADY_EXISTS });
      } finally {
        // Cleanup both storage systems (use the original name for storageName1 if rename failed)
        if (!renameResult?.success) {
          await runCli(['storage', 'delete', storageName1, '--team', defaultTeamName, '--force']);
        }
        await runCli(['storage', 'delete', storageName2, '--team', defaultTeamName, '--force']);
      }
    });

    it('should fail when renaming to an empty name', async () => {
      const storageName = `error-test-empty-${Date.now()}`;

      // Create a storage first
      const createResult = await runCli(['storage', 'create', storageName, '--team', defaultTeamName]);
      expect(createResult.success, `Setup failed: ${getErrorMessage(createResult)}`).toBe(true);

      try {
        // Try to rename to empty string - should fail
        const renameResult = await runCli(['storage', 'rename', storageName, '', '--team', defaultTeamName]);
        expectError(renameResult, { messageContains: ErrorPatterns.STORAGE_NAME_EMPTY });
      } finally {
        // Cleanup
        await runCli(['storage', 'delete', storageName, '--team', defaultTeamName, '--force']);
      }
    });
  });

  // ============================================
  // Storage List Errors
  // ============================================
  describe('Storage list errors', () => {
    it('should return empty list for non-existent team', async () => {
      const result = await runCli(['storage', 'list', '--team', nonExistentName('team')]);
      // Note: API returns success with empty array for non-existent team (similar to team member list)
      expect(result.success).toBe(true);
      expect(result.json).toEqual([]);
    });
  });
});
