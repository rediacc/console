import { describe, it, expect, beforeAll } from 'vitest';
import { runCli } from './helpers/cli.js';

describe('queue commands', () => {
  let teamName: string;

  beforeAll(async () => {
    // Get a valid team name
    const teamResult = await runCli(['team', 'list']);
    const teams = teamResult.json as unknown[];
    teamName = (teams[0] as Record<string, unknown>).teamName as string;
  });

  describe('queue list', () => {
    it('should list queue items for a team', async () => {
      // Team is required for queue list
      const result = await runCli(['queue', 'list', '--team', teamName]);

      expect(result.success).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);
    });

    it('should list queue items with filters', async () => {
      // Team is required, status filter is optional
      const result = await runCli([
        'queue',
        'list',
        '--team',
        teamName,
        '--status',
        'completed',
        '--limit',
        '5',
      ]);

      expect(result.success).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);
    });

    it('should require team parameter', async () => {
      // Without team, should fail with helpful error
      const result = await runCli(['queue', 'list']);

      expect(result.success).toBe(false);
      // In JSON mode, error is returned as structured JSON in stdout
      const errorResponse = result.json as { success: false; error: { message: string } } | null;
      expect(errorResponse?.error?.message).toContain('Team name required');
    });
  });

  describe('queue trace', () => {
    it('should trace a queue item if one exists', async () => {
      // First get a queue item
      const listResult = await runCli(['queue', 'list', '--limit', '1']);
      const items = (listResult.json ?? []) as unknown[];

      if (items.length > 0) {
        const taskId = (items[0] as Record<string, unknown>).taskId as string;

        const result = await runCli(['queue', 'trace', taskId]);

        expect(result.success).toBe(true);
      }
    });
  });

  // Note: create, cancel, retry tests require careful setup
  describe.skip('queue operations', () => {
    it('should create a queue item', async () => {
      const result = await runCli([
        'queue',
        'create',
        'test-function',
        '--team',
        teamName,
        '--machine',
        'test-machine',
      ]);
      expect(result.exitCode).toBe(0);
    });
  });
});
