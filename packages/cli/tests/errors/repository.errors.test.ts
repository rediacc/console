import { beforeAll, describe, it } from 'vitest';
import { runCli } from '../helpers/cli.js';
import { ErrorPatterns, expectError, nonExistentName } from '../helpers/errors.js';

/**
 * Negative test cases for repository commands.
 * Tests backend error responses from middleware stored procedures.
 *
 * Note: Some tests are intentionally omitted to avoid auth token expiration issues:
 * - Creating repositories for test setup can cause long-running tests
 * - Vault operations require master password and may timeout
 * - Tests focus on validation errors that don't require existing resources
 */
describe('repository error scenarios', () => {
  let defaultTeamName: string;

  beforeAll(async () => {
    // Get default team for tests
    const teamsResult = await runCli(['team', 'list']);
    const teams = teamsResult.json as { teamName: string }[];
    defaultTeamName = teams.find((t) => t.teamName !== 'Private Team')?.teamName ?? 'Private Team';
  });

  // ============================================
  // CreateRepository Errors
  // ============================================
  describe('CreateRepository errors', () => {
    it('should fail when creating repository with non-existent team', async () => {
      const result = await runCli([
        'repository',
        'create',
        'test-repo',
        '--team',
        nonExistentName('team'),
      ]);
      expectError(result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });

    // Note: Testing non-existent parent repository triggers API parameter validation
    // error because CLI automatically adds default parent-tag. This is a CLI implementation
    // detail rather than a backend error scenario. Skipping this test.
  });

  // ============================================
  // DeleteRepository Errors
  // ============================================
  describe('DeleteRepository errors', () => {
    it('should fail when deleting from non-existent team', async () => {
      const result = await runCli([
        'repository',
        'delete',
        'some-repo',
        '--team',
        nonExistentName('team'),
        '--force',
      ]);
      // CLI does client-side validation first - shows "not found" (not team-specific)
      expectError(result, { messageContains: 'not found' });
    });

    it('should fail when deleting non-existent repository', async () => {
      const result = await runCli([
        'repository',
        'delete',
        nonExistentName('repo'),
        '--team',
        defaultTeamName,
        '--force',
      ]);
      // CLI does client-side validation - shows "not found"
      expectError(result, { messageContains: 'not found' });
    });
  });

  // ============================================
  // RenameRepository Errors
  // ============================================
  describe('RenameRepository errors', () => {
    it('should fail when renaming from non-existent team', async () => {
      const result = await runCli([
        'repository',
        'rename',
        'old-name',
        'new-name',
        '--team',
        nonExistentName('team'),
      ]);
      expectError(result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });

    it('should fail when renaming non-existent repository', async () => {
      const result = await runCli([
        'repository',
        'rename',
        nonExistentName('repo'),
        'new-name',
        '--team',
        defaultTeamName,
      ]);
      expectError(result, { messageContains: ErrorPatterns.REPOSITORY_NOT_FOUND });
    });
  });

  // ============================================
  // PromoteRepository Errors
  // ============================================
  describe('PromoteRepository errors', () => {
    it('should fail when promoting from non-existent team', async () => {
      const result = await runCli([
        'repository',
        'promote',
        'some-repo',
        '--team',
        nonExistentName('team'),
        '--force',
      ]);
      // CLI does client-side validation - shows "not found"
      expectError(result, { messageContains: 'not found' });
    });

    it('should fail when promoting non-existent repository', async () => {
      const result = await runCli([
        'repository',
        'promote',
        nonExistentName('repo'),
        '--team',
        defaultTeamName,
        '--force',
      ]);
      // CLI does client-side validation - shows "not found"
      expectError(result, { messageContains: 'not found' });
    });
  });
});
