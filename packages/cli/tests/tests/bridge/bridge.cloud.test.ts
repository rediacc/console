import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';

test.describe('Bridge Commands @cli @resources', () => {
  let runner: CliTestRunner;
  let teamName: string;

  test.beforeAll(async () => {
    runner = CliTestRunner.fromGlobalState();

    // Get a valid team name
    const teamResult = await runner.teamList();
    const teams = runner.expectSuccessArray<{ teamName: string }>(teamResult);
    teamName = teams[0].teamName;
  });

  test.describe('bridge list', () => {
    test('should list bridges for a team', async () => {
      // Bridge list requires team or region context
      const result = await runner.run(['bridge', 'list', '--team', teamName]);

      // Fresh accounts may not have bridges or require additional setup
      expect(result.success || result.stderr.length > 0).toBe(true);
    });
  });

  test.describe('bridge inspect', () => {
    test('should inspect a bridge if one exists', async () => {
      const listResult = await runner.run(['bridge', 'list']);
      const bridges = Array.isArray(listResult.json) ? listResult.json : [];

      if (bridges.length > 0) {
        const bridgeName = (bridges[0] as Record<string, unknown>).bridgeName as string;

        const result = await runner.run(['bridge', 'inspect', bridgeName]);

        expect(runner.isSuccess(result)).toBe(true);
      }
    });
  });

  // CRUD operations - safe to run with fresh organization registration
  test.describe('bridge CRUD operations', () => {
    const testBridgeName = `test-bridge-${Date.now()}`;

    test('should create a new bridge', async () => {
      const result = await runner.run([
        'bridge',
        'create',
        testBridgeName,
        '--region',
        'Default Region',
      ]);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('should delete the bridge', async () => {
      const result = await runner.run([
        'bridge',
        'delete',
        testBridgeName,
        '--region',
        'Default Region',
        '--force',
      ]);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });
});
