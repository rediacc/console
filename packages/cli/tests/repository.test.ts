import { describe, it, expect, beforeAll } from 'vitest';
import { runCli } from './helpers/cli.js';

describe('repository commands', () => {
  let teamName: string;
  let machineName: string | null = null;

  beforeAll(async () => {
    // Get a valid team name
    const teamResult = await runCli(['team', 'list']);
    const teams = teamResult.json as unknown[];
    teamName = (teams[0] as Record<string, unknown>).teamName as string;

    // Get a valid machine name if available
    const machineResult = await runCli(['machine', 'list', '--team', teamName]);
    const machines = (machineResult.json ?? []) as unknown[];
    if (machines.length > 0) {
      machineName = (machines[0] as Record<string, unknown>).machineName as string;
    }
  });

  describe('repository list', () => {
    it('should list repositories for a team', async () => {
      const result = await runCli(['repository', 'list', '--team', teamName]);

      expect(result.success).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);
    });

    it('should list repositories for a machine', async () => {
      if (!machineName) {
        // Skip test - no machines available
        return;
      }

      const result = await runCli([
        'repository',
        'list',
        '--team',
        teamName,
        '--machine',
        machineName,
      ]);

      expect(result.success).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);
    });
  });

  describe('repository inspect', () => {
    it('should inspect a repository if one exists', async () => {
      const listResult = await runCli(['repository', 'list', '--team', teamName]);
      const repos = (listResult.json ?? []) as unknown[];

      if (repos.length > 0) {
        const repoName = (repos[0] as Record<string, unknown>).repositoryName as string;

        const result = await runCli(['repository', 'inspect', repoName, '--team', teamName]);

        expect(result.success).toBe(true);
      }
    });
  });

  // CRUD operations - safe to run with fresh company registration
  describe('repository CRUD operations', () => {
    const testRepoName = `test-repo-${Date.now()}`;

    it('should create a new repository', async () => {
      const result = await runCli(['repository', 'create', testRepoName, '--team', teamName]);
      expect(result.success).toBe(true);
    });

    it('should delete the repository', async () => {
      const result = await runCli([
        'repository',
        'delete',
        testRepoName,
        '--team',
        teamName,
        '--force',
      ]);
      expect(result.success).toBe(true);
    });
  });
});
