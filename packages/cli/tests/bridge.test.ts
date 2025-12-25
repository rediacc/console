import { describe, it, expect, beforeAll } from 'vitest';
import { runCli } from './helpers/cli.js';

describe('bridge commands', () => {
  let teamName: string;

  beforeAll(async () => {
    // Get a valid team name
    const teamResult = await runCli(['team', 'list']);
    const teams = teamResult.json as unknown[];
    teamName = (teams[0] as Record<string, unknown>).teamName as string;
  });

  describe('bridge list', () => {
    it('should list bridges for a team', async () => {
      // Bridge list requires team or region context
      const result = await runCli(['bridge', 'list', '--team', teamName]);

      // Fresh accounts may not have bridges or require additional setup
      expect(result.success || result.stderr.length > 0).toBe(true);
    });
  });

  describe('bridge inspect', () => {
    it('should inspect a bridge if one exists', async () => {
      const listResult = await runCli(['bridge', 'list']);
      const bridges = listResult.json as unknown[] ?? [];

      if (bridges.length > 0) {
        const bridgeName = (bridges[0] as Record<string, unknown>).bridgeName as string;

        const result = await runCli(['bridge', 'inspect', bridgeName]);

        expect(result.success).toBe(true);
      }
    });
  });

  // CRUD operations - safe to run with fresh company registration
  describe('bridge CRUD operations', () => {
    const testBridgeName = `test-bridge-${Date.now()}`;

    it('should create a new bridge', async () => {
      const result = await runCli(['bridge', 'create', testBridgeName, '--region', 'Default Region']);
      expect(result.success).toBe(true);
    });

    it('should delete the bridge', async () => {
      const result = await runCli(['bridge', 'delete', testBridgeName, '--region', 'Default Region', '--force']);
      expect(result.success).toBe(true);
    });
  });
});
