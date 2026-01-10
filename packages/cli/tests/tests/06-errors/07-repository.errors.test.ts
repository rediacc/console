import { test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { ErrorPatterns, expectError, nonExistentName } from '../../src/utils/errors';

/**
 * Negative test cases for repository commands.
 */
test.describe('Repository Error Scenarios @cli @errors', () => {
  let runner: CliTestRunner;
  let defaultTeamName: string;

  test.beforeAll(async () => {
    runner = CliTestRunner.fromGlobalState();

    // Get default team for tests
    const teamsResult = await runner.teamList();
    const teams = runner.expectSuccessArray<{ teamName: string }>(teamsResult);
    defaultTeamName = teams.find((t) => t.teamName !== 'Private Team')?.teamName ?? 'Private Team';
  });

  test.describe('CreateRepository errors', () => {
    test('should fail when creating repository with non-existent team', async () => {
      const result = await runner.run([
        'repository',
        'create',
        'test-repo',
        '--team',
        nonExistentName('team'),
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });
  });

  test.describe('DeleteRepository errors', () => {
    test('should fail when deleting from non-existent team', async () => {
      const result = await runner.run([
        'repository',
        'delete',
        'some-repo',
        '--team',
        nonExistentName('team'),
        '--force',
      ]);
      // CLI does client-side validation first - shows "not found" (not team-specific)
      expectError(runner, result, { messageContains: 'not found' });
    });

    test('should fail when deleting non-existent repository', async () => {
      const result = await runner.run([
        'repository',
        'delete',
        nonExistentName('repo'),
        '--team',
        defaultTeamName,
        '--force',
      ]);
      // CLI does client-side validation - shows "not found"
      expectError(runner, result, { messageContains: 'not found' });
    });
  });

  test.describe('RenameRepository errors', () => {
    test('should fail when renaming from non-existent team', async () => {
      const result = await runner.run([
        'repository',
        'rename',
        'old-name',
        'new-name',
        '--team',
        nonExistentName('team'),
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });

    test('should fail when renaming non-existent repository', async () => {
      const result = await runner.run([
        'repository',
        'rename',
        nonExistentName('repo'),
        'new-name',
        '--team',
        defaultTeamName,
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.REPOSITORY_NOT_FOUND });
    });
  });

  test.describe('PromoteRepository errors', () => {
    test('should fail when promoting from non-existent team', async () => {
      const result = await runner.run([
        'repository',
        'promote',
        'some-repo',
        '--team',
        nonExistentName('team'),
        '--force',
      ]);
      // CLI does client-side validation - shows "not found"
      expectError(runner, result, { messageContains: 'not found' });
    });

    test('should fail when promoting non-existent repository', async () => {
      const result = await runner.run([
        'repository',
        'promote',
        nonExistentName('repo'),
        '--team',
        defaultTeamName,
        '--force',
      ]);
      // CLI does client-side validation - shows "not found"
      expectError(runner, result, { messageContains: 'not found' });
    });
  });
});
