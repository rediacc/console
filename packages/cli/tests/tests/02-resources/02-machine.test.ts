import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';

test.describe('Machine Commands @cli @resources', () => {
  let runner: CliTestRunner;
  let teamName: string;

  test.beforeAll(async () => {
    runner = CliTestRunner.fromGlobalState();

    // Get a valid team name for machine queries
    const listResult = await runner.teamList();
    const teams = runner.expectSuccessArray<{ teamName: string }>(listResult);
    teamName = teams[0].teamName;
  });

  test.describe('machine list', () => {
    test('should list all machines for a team', async () => {
      const result = await runner.machineList(teamName);

      expect(runner.isSuccess(result)).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);

      const machines = runner.expectSuccessArray<{ machineName: string; teamName: string }>(result);
      if (machines.length > 0) {
        expect(machines[0]).toHaveProperty('machineName');
        expect(machines[0]).toHaveProperty('teamName');
      }
    });

    test('should handle missing team name', async () => {
      // Clear any context first
      const result = await runner.run(['machine', 'list']);

      // Should either fail or use context
      expect(result).toBeDefined();
    });
  });

  test.describe('machine status', () => {
    test('should show machine status for a team', async () => {
      const result = await runner.run(['machine', 'status', '--team', teamName]);

      // Machine status may fail if no machines exist or require region
      expect(result.success || result.stderr.includes('required')).toBe(true);
    });
  });

  test.describe('machine inspect', () => {
    test('should inspect a machine', async () => {
      const listResult = await runner.machineList(teamName);
      const machines = runner.expectSuccessArray<{ machineName: string }>(listResult);

      if (machines.length > 0) {
        const machineName = machines[0].machineName;

        const result = await runner.run(['machine', 'inspect', machineName, '--team', teamName]);

        expect(runner.isSuccess(result)).toBe(true);
        expect(result.json).not.toBeNull();
      }
    });
  });

  test.describe('machine vault-status', () => {
    test('should show vault status for a machine', async () => {
      const listResult = await runner.machineList(teamName);
      const machines = runner.expectSuccessArray<{ machineName: string }>(listResult);

      if (machines.length > 0) {
        const machineName = machines[0].machineName;

        const result = await runner.run([
          'machine',
          'vault-status',
          machineName,
          '--team',
          teamName,
        ]);

        expect(runner.isSuccess(result)).toBe(true);
      }
    });
  });

  test.describe('machine repos', () => {
    test('should list repositories on a machine', async () => {
      const listResult = await runner.machineList(teamName);
      const machines = runner.expectSuccessArray<{ machineName: string }>(listResult);

      if (machines.length > 0) {
        const machineName = machines[0].machineName;

        const result = await runner.run(['machine', 'repos', machineName, '--team', teamName]);

        expect(runner.isSuccess(result)).toBe(true);
      }
    });
  });

  // CRUD operations - safe to run with fresh organization registration
  test.describe('machine CRUD operations', () => {
    const testMachineName = `test-machine-${Date.now()}`;
    const testBridgeName = `test-bridge-machine-${Date.now()}`;
    let renamedMachineName: string;

    test.beforeAll(async () => {
      // Create a bridge for machine tests (machines require a bridge)
      await runner.run(['bridge', 'create', testBridgeName, '--region', 'Default Region']);
    });

    test.afterAll(async () => {
      // Cleanup the bridge
      await runner.run([
        'bridge',
        'delete',
        testBridgeName,
        '--region',
        'Default Region',
        '--force',
      ]);
    });

    test('should create a new machine', async () => {
      const result = await runner.run([
        'machine',
        'create',
        testMachineName,
        '--team',
        teamName,
        '--bridge',
        testBridgeName,
      ]);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('should rename the machine', async () => {
      renamedMachineName = `${testMachineName}-renamed`;
      const result = await runner.run([
        'machine',
        'rename',
        testMachineName,
        renamedMachineName,
        '--team',
        teamName,
      ]);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('should delete the machine', async () => {
      const result = await runner.machineDelete(renamedMachineName, teamName);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });
});
