import { beforeAll, describe, expect, it } from 'vitest';
import { runCli } from './helpers/cli.js';

describe('shortcut commands', () => {
  let teamName: string;

  beforeAll(async () => {
    // Get a valid team name
    const teamResult = await runCli(['team', 'list']);
    const teams = teamResult.json as unknown[];
    teamName = (teams[0] as Record<string, unknown>).teamName as string;
  });

  describe('trace shortcut', () => {
    it('should trace a task if queue items exist', async () => {
      // First get a queue item
      const listResult = await runCli(['queue', 'list', '--limit', '1']);
      const items = (listResult.json ?? []) as unknown[];

      if (items.length > 0) {
        const taskId = (items[0] as Record<string, unknown>).taskId as string;

        // Use the shortcut command
        const result = await runCli(['trace', taskId]);

        expect(result.success).toBe(true);
      }
    });
  });

  // Note: run, cancel, retry shortcuts require specific setup
  describe.skip('run shortcut', () => {
    it('should run a function via shortcut', async () => {
      const result = await runCli([
        'run',
        'test-function',
        '--team',
        teamName,
        '--machine',
        'test-machine',
      ]);
      expect(result.exitCode).toBe(0);
    });
  });

  describe.skip('cancel shortcut', () => {
    it('should cancel a task via shortcut', async () => {
      // Requires an active task to cancel
    });
  });

  describe.skip('retry shortcut', () => {
    it('should retry a failed task via shortcut', async () => {
      // Requires a failed task to retry
    });
  });
});
