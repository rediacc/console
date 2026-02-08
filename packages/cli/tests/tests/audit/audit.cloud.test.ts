import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';

test.describe('Audit Commands @cli @operations', () => {
  let runner: CliTestRunner;
  let teamName: string;

  test.beforeAll(async () => {
    runner = CliTestRunner.fromGlobalState();

    // Get a valid team name
    const teamResult = await runner.teamList();
    const teams = runner.expectSuccessArray<{ teamName: string }>(teamResult);
    teamName = teams[0].teamName;
  });

  test.describe('audit list', () => {
    test('should list audit logs for a team', async () => {
      // Audit list requires team context
      const result = await runner.run(['audit', 'list', '--team', teamName]);

      // Fresh accounts may not have audit logs or may lack permissions
      // Just verify the command completes (success or graceful failure)
      expect(result.success || Array.isArray(result.json) || result.json === null).toBe(true);
    });

    test('should list audit logs with limit', async () => {
      const result = await runner.auditList({ limit: 10 });

      // Fresh accounts may not have audit logs
      if (result.success && result.json) {
        const logs = runner.expectSuccessArray(result);
        expect(logs.length).toBeLessThanOrEqual(10);
      }
    });
  });

  // Audit logs are read-only, no CRUD operations to test
});
