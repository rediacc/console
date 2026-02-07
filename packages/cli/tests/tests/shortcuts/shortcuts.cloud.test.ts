import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';

test.describe('Shortcut Commands @cli @operations', () => {
  let runner: CliTestRunner;
  let teamName: string;

  test.beforeAll(async () => {
    runner = CliTestRunner.fromGlobalState();

    // Get a valid team name
    const teamResult = await runner.teamList();
    const teams = runner.expectSuccessArray<{ teamName: string }>(teamResult);
    teamName = teams[0].teamName;
  });

  test.describe('trace shortcut', () => {
    test('should trace a task if queue items exist', async () => {
      // First get a queue item (requires --team)
      const listResult = await runner.run(['queue', 'list', '--team', teamName, '--limit', '1']);
      if (!listResult.success) {
        // No queue items to trace - skip the trace part
        return;
      }
      const items = listResult.json as { taskId: string }[];

      if (items.length > 0) {
        const taskId = items[0].taskId;

        // Use the shortcut command
        const result = await runner.run(['trace', taskId]);

        expect(runner.isSuccess(result)).toBe(true);
      }
    });
  });

  // Note: run, cancel, retry shortcuts require specific setup
  test.describe
    .skip('run shortcut', () => {
      test('should run a function via shortcut', async () => {
        const result = await runner.run([
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

  test.describe
    .skip('cancel shortcut', () => {
      test.skip('should cancel a task via shortcut', async () => {
        // TODO: Requires an active task to cancel
      });
    });

  test.describe
    .skip('retry shortcut', () => {
      test.skip('should retry a failed task via shortcut', async () => {
        // TODO: Requires a failed task to retry
      });
    });
});
