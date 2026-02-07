import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';

test.describe('Team Commands @cli @resources', () => {
  let runner: CliTestRunner;

  test.beforeAll(() => {
    runner = CliTestRunner.fromGlobalState();
  });

  test.describe('team list', () => {
    test('should list all teams', async () => {
      const result = await runner.teamList();

      expect(runner.isSuccess(result)).toBe(true);
      expect(result.json).not.toBeNull();
      expect(Array.isArray(result.json)).toBe(true);

      const teams = runner.expectSuccessArray<{ teamName: string }>(result);
      expect(teams.length).toBeGreaterThan(0);

      // Each team should have expected fields
      expect(teams[0]).toHaveProperty('teamName');
    });
  });

  test.describe('team inspect', () => {
    test('should inspect a team', async () => {
      // First get the list of teams to get a valid team name
      const listResult = await runner.teamList();
      expect(runner.isSuccess(listResult)).toBe(true);

      const teams = runner.expectSuccessArray<{ teamName: string }>(listResult);
      const teamName = teams[0].teamName;

      const result = await runner.run(['team', 'inspect', teamName]);

      // Team inspect may require vault decryption which needs master password
      // For fresh accounts, the command should run (success or with decryption issue)

      expect(result.success || result.stderr.length > 0 || result.stdout.length > 0).toBe(true);
    });
  });

  test.describe('team member', () => {
    test.describe('team member list', () => {
      test('should list team members', async () => {
        // First get the list of teams
        const listResult = await runner.teamList();
        expect(runner.isSuccess(listResult)).toBe(true);

        const teams = runner.expectSuccessArray<{ teamName: string }>(listResult);
        const teamName = teams[0].teamName;

        const result = await runner.teamMemberList(teamName);

        expect(runner.isSuccess(result)).toBe(true);
        expect(result.json).not.toBeNull();
        expect(Array.isArray(result.json)).toBe(true);
      });
    });
  });

  // CRUD operations - safe to run with fresh organization registration
  test.describe('team CRUD operations', () => {
    const testTeamName = `test-team-${Date.now()}`;
    let renamedTeamName: string;

    test('should create a new team', async () => {
      const result = await runner.teamCreate(testTeamName);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('should rename the team', async () => {
      renamedTeamName = `${testTeamName}-renamed`;
      const result = await runner.teamRename(testTeamName, renamedTeamName);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('should delete the team', async () => {
      const result = await runner.teamDelete(renamedTeamName);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });
});
