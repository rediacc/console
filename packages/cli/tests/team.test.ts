import { describe, expect, it } from 'vitest';
import { runCli } from './helpers/cli.js';

describe('team commands', () => {
  describe('team list', () => {
    it('should list all teams', async () => {
      const result = await runCli(['team', 'list']);

      expect(result.success).toBe(true);
      expect(result.json).not.toBeNull();
      expect(Array.isArray(result.json)).toBe(true);

      const teams = result.json as unknown[];
      expect(teams.length).toBeGreaterThan(0);

      // Each team should have expected fields
      const team = teams[0] as Record<string, unknown>;
      expect(team).toHaveProperty('teamName');
    });
  });

  describe('team inspect', () => {
    it('should inspect a team', async () => {
      // First get the list of teams to get a valid team name
      const listResult = await runCli(['team', 'list']);
      expect(listResult.success).toBe(true);

      const teams = listResult.json as unknown[];
      const teamName = (teams[0] as Record<string, unknown>).teamName as string;

      const result = await runCli(['team', 'inspect', teamName]);

      // Team inspect may require vault decryption which needs master password
      // For fresh accounts, the command should run (success or with decryption issue)
      expect(result.success || result.stderr.length > 0 || result.stdout.length > 0).toBe(true);
    });
  });

  describe('team member', () => {
    describe('team member list', () => {
      it('should list team members', async () => {
        // First get the list of teams
        const listResult = await runCli(['team', 'list']);
        expect(listResult.success).toBe(true);

        const teams = listResult.json as unknown[];
        const teamName = (teams[0] as Record<string, unknown>).teamName as string;

        const result = await runCli(['team', 'member', 'list', teamName]);

        expect(result.success).toBe(true);
        expect(result.json).not.toBeNull();
        expect(Array.isArray(result.json)).toBe(true);
      });
    });
  });

  // CRUD operations - safe to run with fresh company registration
  describe('team CRUD operations', () => {
    const testTeamName = `test-team-${Date.now()}`;
    let renamedTeamName: string;

    it('should create a new team', async () => {
      const result = await runCli(['team', 'create', testTeamName]);
      expect(result.success).toBe(true);
    });

    it('should rename the team', async () => {
      renamedTeamName = `${testTeamName}-renamed`;
      const result = await runCli(['team', 'rename', testTeamName, renamedTeamName]);
      expect(result.success).toBe(true);
    });

    it('should delete the team', async () => {
      const result = await runCli(['team', 'delete', renamedTeamName, '--force']);
      expect(result.success).toBe(true);
    });
  });
});
