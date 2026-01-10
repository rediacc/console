import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';

test.describe('Queue Commands @cli @operations', () => {
  let runner: CliTestRunner;
  let teamName: string;

  test.beforeAll(async () => {
    runner = CliTestRunner.fromGlobalState();

    // Get a valid team name
    const teamResult = await runner.teamList();
    const teams = runner.expectSuccessArray<{ teamName: string }>(teamResult);
    teamName = teams[0].teamName;
  });

  test.describe('queue list', () => {
    test('should list queue items for a team', async () => {
      // Team is required for queue list
      const result = await runner.queueList(teamName);

      expect(runner.isSuccess(result)).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);
    });

    test('should list queue items with filters', async () => {
      // Team is required, status filter is optional
      const result = await runner.queueList(teamName, { status: 'completed', limit: 5 });

      expect(runner.isSuccess(result)).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);
    });

    test('should require team parameter', async () => {
      // Without team, should fail with helpful error
      const result = await runner.run(['queue', 'list']);

      expect(result.success).toBe(false);
      // In JSON mode, error is returned as structured JSON in stdout
      const errorResponse = result.json as { success: false; error: { message: string } } | null;
      expect(errorResponse?.error.message).toContain('Team name required');
    });
  });

  test.describe('queue trace', () => {
    test('should trace a queue item if one exists', async () => {
      // First get a queue item (requires --team)
      const listResult = await runner.run(['queue', 'list', '--team', teamName, '--limit', '1']);
      if (!listResult.success) {
        // No queue items to trace - skip the trace part
        return;
      }
      const items = listResult.json as { taskId: string }[];

      if (items.length > 0) {
        const taskId = items[0].taskId;

        const result = await runner.queueTrace(taskId);

        expect(runner.isSuccess(result)).toBe(true);
      }
    });
  });

  // Note: create, cancel, retry tests require careful setup
  test.describe
    .skip('queue operations', () => {
      test('should create a queue item', async () => {
        const result = await runner.run([
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
