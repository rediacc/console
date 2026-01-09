import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { ErrorPatterns, expectError, nonExistentName } from '../../src/utils/errors';

/**
 * Negative test cases for team commands.
 */
test.describe('Team Error Scenarios @cli @errors', () => {
  let runner: CliTestRunner;
  let currentUserEmail: string;
  let defaultTeamName: string;

  test.beforeAll(async () => {
    runner = CliTestRunner.fromGlobalState();
    currentUserEmail = runner.config.credentials!.email;

    const teamsResult = await runner.teamList();
    const teams = runner.expectSuccessArray<{ teamName: string }>(teamsResult);
    defaultTeamName = teams.find((t) => t.teamName !== 'Private Team')?.teamName ?? 'Private Team';
  });

  test.describe('CreateTeam errors', () => {
    test('should fail when creating team with duplicate name', async () => {
      const teamName = `error-test-dup-${Date.now()}`;

      // Create the team first
      const createResult = await runner.teamCreate(teamName);
      expect(createResult.success, `Setup failed: ${runner.getErrorMessage(createResult)}`).toBe(
        true
      );

      try {
        // Try to create with same name - should fail
        const duplicateResult = await runner.teamCreate(teamName);
        expectError(runner, duplicateResult, {
          messageContains: ErrorPatterns.TEAM_ALREADY_EXISTS,
        });
      } finally {
        // Cleanup
        await runner.teamDelete(teamName);
      }
    });
  });

  test.describe('DeleteTeam errors', () => {
    test('should fail when deleting non-existent team', async () => {
      const result = await runner.run(['team', 'delete', nonExistentName('team'), '--force']);
      expectError(runner, result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });

    test('should fail when deleting Private Team (system entity)', async () => {
      const result = await runner.run(['team', 'delete', 'Private Team', '--force']);
      expectError(runner, result, { messageContains: ErrorPatterns.TEAM_CANNOT_DELETE_DEFAULT });
    });
  });

  test.describe('RenameTeam errors', () => {
    test('should fail when renaming non-existent team', async () => {
      const result = await runner.teamRename(nonExistentName('team'), 'new-name');
      expectError(runner, result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });

    test('should fail when renaming Private Team (system entity)', async () => {
      const result = await runner.teamRename('Private Team', 'New Name');
      expectError(runner, result, { messageContains: ErrorPatterns.TEAM_CANNOT_RENAME_DEFAULT });
    });

    test('should fail when renaming to an existing team name', async () => {
      const tempTeamName = `error-test-rename-${Date.now()}`;

      // Create a temp team
      const createResult = await runner.teamCreate(tempTeamName);
      expect(createResult.success, `Setup failed: ${runner.getErrorMessage(createResult)}`).toBe(
        true
      );

      try {
        // Try to rename temp team to "Private Team" (which exists)
        const renameResult = await runner.teamRename(tempTeamName, 'Private Team');
        expectError(runner, renameResult, { messageContains: ErrorPatterns.TEAM_ALREADY_EXISTS });
      } finally {
        // Cleanup
        await runner.teamDelete(tempTeamName);
      }
    });
  });

  test.describe('Team member list errors', () => {
    test('should return empty list for non-existent team', async () => {
      const result = await runner.run(['team', 'member', 'list', nonExistentName('team')]);
      // API returns success with empty array for non-existent team
      expect(result.success).toBe(true);
      expect(result.json).toEqual([]);
    });
  });

  test.describe('Team member add errors', () => {
    test('should fail when adding user to non-existent team', async () => {
      const result = await runner.run([
        'team',
        'member',
        'add',
        nonExistentName('team'),
        'test@example.com',
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });

    test('should fail when adding non-existent user to team', async () => {
      const result = await runner.run([
        'team',
        'member',
        'add',
        defaultTeamName,
        'nonexistent-user@nowhere.invalid',
      ]);
      expectError(runner, result, {
        messageContains: ErrorPatterns.USER_NOT_FOUND_IN_ORGANIZATION,
      });
    });

    test('should fail when adding user who is already a member', async () => {
      const result = await runner.run(['team', 'member', 'add', defaultTeamName, currentUserEmail]);
      expectError(runner, result, { messageContains: ErrorPatterns.USER_ALREADY_MEMBER });
    });
  });

  test.describe('Team member remove errors', () => {
    test('should fail when removing user from non-existent team', async () => {
      const result = await runner.run([
        'team',
        'member',
        'remove',
        nonExistentName('team'),
        'test@example.com',
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });

    test('should fail when removing yourself from team', async () => {
      const result = await runner.run([
        'team',
        'member',
        'remove',
        defaultTeamName,
        currentUserEmail,
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.CANNOT_REMOVE_SELF });
    });
  });
});
