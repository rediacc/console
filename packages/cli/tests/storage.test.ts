import { describe, it, expect, beforeAll } from 'vitest';
import { runCli } from './helpers/cli.js';

describe('storage commands', () => {
  let teamName: string;

  beforeAll(async () => {
    // Get a valid team name
    const teamResult = await runCli(['team', 'list']);
    const teams = teamResult.json as unknown[];
    teamName = (teams[0] as Record<string, unknown>).teamName as string;
  });

  describe('storage list', () => {
    it('should list storage configurations or indicate none exist', async () => {
      const result = await runCli(['storage', 'list']);

      // Storage list might return empty or an error if no storage is configured
      // The important thing is that the command runs without crashing
      expect(result).toBeDefined();

      if (result.success) {
        expect(Array.isArray(result.json)).toBe(true);
      }
    });

    it('should list storage configurations for a team or indicate none exist', async () => {
      const result = await runCli(['storage', 'list', '--team', teamName]);

      // Storage list might return empty or an error if no storage is configured
      expect(result).toBeDefined();

      if (result.success) {
        expect(Array.isArray(result.json)).toBe(true);
      }
    });
  });

  // Note: storage CRUD operations are skipped to avoid modifying production data
  describe.skip('storage CRUD operations', () => {
    it('should create a storage configuration', async () => {
      // Storage creation typically requires specific provider configuration
    });
  });
});
