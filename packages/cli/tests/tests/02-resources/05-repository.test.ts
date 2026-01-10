import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';

test.describe('Repository Commands @cli @resources', () => {
  let runner: CliTestRunner;
  let teamName: string;
  let machineName: string | null = null;

  test.beforeAll(async () => {
    runner = CliTestRunner.fromGlobalState();

    // Get a valid team name
    const teamResult = await runner.teamList();
    const teams = runner.expectSuccessArray<{ teamName: string }>(teamResult);
    teamName = teams[0].teamName;

    // Get a valid machine name if available
    const machineResult = await runner.machineList(teamName);
    const machines = runner.expectSuccessArray<{ machineName: string }>(machineResult);
    if (machines.length > 0) {
      machineName = machines[0].machineName;
    }
  });

  test.describe('repository list', () => {
    test('should list repositories for a team', async () => {
      const result = await runner.repositoryList(teamName);

      expect(runner.isSuccess(result)).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);
    });

    test('should list repositories for a machine', async () => {
      if (!machineName) {
        // Skip test - no machines available
        return;
      }

      const result = await runner.run([
        'repository',
        'list',
        '--team',
        teamName,
        '--machine',
        machineName,
      ]);

      expect(runner.isSuccess(result)).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);
    });
  });

  test.describe('repository inspect', () => {
    test('should inspect a repository if one exists', async () => {
      const listResult = await runner.repositoryList(teamName);
      const repos = runner.expectSuccessArray<{ repositoryName: string }>(listResult);

      if (repos.length > 0) {
        const repositoryName = repos[0].repositoryName;

        const result = await runner.run([
          'repository',
          'inspect',
          repositoryName,
          '--team',
          teamName,
        ]);

        expect(runner.isSuccess(result)).toBe(true);
      }
    });
  });

  // CRUD operations - safe to run with fresh organization registration
  test.describe('repository CRUD operations', () => {
    const testRepoName = `test-repo-${Date.now()}`;

    test('should create a new repository', async () => {
      const result = await runner.run(['repository', 'create', testRepoName, '--team', teamName]);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('should delete the repository', async () => {
      const result = await runner.repositoryDelete(testRepoName, teamName);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });
});
