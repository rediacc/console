import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { runCli, getErrorMessage } from '../helpers/cli.js';
import { expectError, nonExistentName, ErrorPatterns } from '../helpers/errors.js';
import { getConfig } from '../helpers/config.js';

/**
 * Negative test cases for team commands.
 * Tests backend error responses from middleware stored procedures.
 */
describe('team error scenarios', () => {
  let currentUserEmail: string;
  let defaultTeamName: string;

  beforeAll(async () => {
    // Get current user email and default team for tests
    const config = getConfig();
    currentUserEmail = config.email;

    const teamsResult = await runCli(['team', 'list']);
    const teams = teamsResult.json as { teamName: string }[];
    defaultTeamName = teams.find((t) => t.teamName !== 'Private Team')?.teamName ?? 'Private Team';
  });

  // ============================================
  // CreateTeam Errors
  // ============================================
  describe('CreateTeam errors', () => {
    it('should fail when creating team with duplicate name', async () => {
      const teamName = `error-test-dup-${Date.now()}`;

      // Create the team first
      const createResult = await runCli(['team', 'create', teamName]);
      expect(createResult.success, `Setup failed: ${getErrorMessage(createResult)}`).toBe(true);

      try {
        // Try to create with same name - should fail
        const duplicateResult = await runCli(['team', 'create', teamName]);
        expectError(duplicateResult, { messageContains: ErrorPatterns.TEAM_ALREADY_EXISTS });
      } finally {
        // Cleanup
        await runCli(['team', 'delete', teamName, '--force']);
      }
    });
  });

  // ============================================
  // DeleteTeam Errors
  // ============================================
  describe('DeleteTeam errors', () => {
    it('should fail when deleting non-existent team', async () => {
      const result = await runCli(['team', 'delete', nonExistentName('team'), '--force']);
      expectError(result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });

    it('should fail when deleting Private Team (system entity)', async () => {
      const result = await runCli(['team', 'delete', 'Private Team', '--force']);
      expectError(result, { messageContains: ErrorPatterns.TEAM_CANNOT_DELETE_DEFAULT });
    });
  });

  // ============================================
  // RenameTeam Errors
  // ============================================
  describe('RenameTeam errors', () => {
    it('should fail when renaming non-existent team', async () => {
      const result = await runCli(['team', 'rename', nonExistentName('team'), 'new-name']);
      expectError(result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });

    it('should fail when renaming Private Team (system entity)', async () => {
      const result = await runCli(['team', 'rename', 'Private Team', 'New Name']);
      expectError(result, { messageContains: ErrorPatterns.TEAM_CANNOT_RENAME_DEFAULT });
    });

    it('should fail when renaming to an existing team name', async () => {
      const tempTeamName = `error-test-rename-${Date.now()}`;

      // Create a temp team
      const createResult = await runCli(['team', 'create', tempTeamName]);
      expect(createResult.success, `Setup failed: ${getErrorMessage(createResult)}`).toBe(true);

      try {
        // Try to rename temp team to "Private Team" (which exists)
        const renameResult = await runCli(['team', 'rename', tempTeamName, 'Private Team']);
        expectError(renameResult, { messageContains: ErrorPatterns.TEAM_ALREADY_EXISTS });
      } finally {
        // Cleanup
        await runCli(['team', 'delete', tempTeamName, '--force']);
      }
    });
  });

  // ============================================
  // Team Member List Errors
  // ============================================
  describe('Team member list errors', () => {
    // Note: team member list with non-existent team returns empty array (API behavior)
    // This is actually acceptable - no error, just empty results
    it('should return empty list for non-existent team', async () => {
      const result = await runCli(['team', 'member', 'list', nonExistentName('team')]);
      // API returns success with empty array for non-existent team
      expect(result.success).toBe(true);
      expect(result.json).toEqual([]);
    });
  });

  // ============================================
  // Team Member Add Errors
  // ============================================
  describe('Team member add errors', () => {
    it('should fail when adding user to non-existent team', async () => {
      const result = await runCli([
        'team',
        'member',
        'add',
        nonExistentName('team'),
        'test@example.com',
      ]);
      expectError(result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });

    it('should fail when adding non-existent user to team', async () => {
      const result = await runCli([
        'team',
        'member',
        'add',
        defaultTeamName,
        'nonexistent-user@nowhere.invalid',
      ]);
      expectError(result, { messageContains: ErrorPatterns.USER_NOT_FOUND_IN_COMPANY });
    });

    it('should fail when adding user who is already a member', async () => {
      // The current user should already be a member of their team
      const result = await runCli(['team', 'member', 'add', defaultTeamName, currentUserEmail]);
      expectError(result, { messageContains: ErrorPatterns.USER_ALREADY_MEMBER });
    });
  });

  // ============================================
  // Team Member Remove Errors
  // ============================================
  describe('Team member remove errors', () => {
    it('should fail when removing user from non-existent team', async () => {
      const result = await runCli([
        'team',
        'member',
        'remove',
        nonExistentName('team'),
        'test@example.com',
      ]);
      expectError(result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });

    it('should fail when removing yourself from team', async () => {
      const result = await runCli(['team', 'member', 'remove', defaultTeamName, currentUserEmail]);
      expectError(result, { messageContains: ErrorPatterns.CANNOT_REMOVE_SELF });
    });
  });
});
