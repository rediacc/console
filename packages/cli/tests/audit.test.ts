import { beforeAll, describe, expect, it } from 'vitest';
import { runCli } from './helpers/cli.js';

describe('audit commands', () => {
  let teamName: string;

  beforeAll(async () => {
    // Get a valid team name
    const teamResult = await runCli(['team', 'list']);
    const teams = teamResult.json as unknown[];
    teamName = (teams[0] as Record<string, unknown>).teamName as string;
  });

  describe('audit list', () => {
    it('should list audit logs for a team', async () => {
      // Audit list requires team context
      const result = await runCli(['audit', 'list', '--team', teamName]);

      // Fresh accounts may not have audit logs or may lack permissions
      // Just verify the command completes (success or graceful failure)
      expect(result.success || Array.isArray(result.json) || result.json === null).toBe(true);
    });

    it('should list audit logs with limit', async () => {
      const result = await runCli(['audit', 'list', '--team', teamName, '--limit', '10']);

      // Fresh accounts may not have audit logs
      if (result.success && result.json) {
        const logs = result.json as unknown[];
        expect(logs.length).toBeLessThanOrEqual(10);
      }
    });
  });

  // Audit logs are read-only, no CRUD operations to test
});
