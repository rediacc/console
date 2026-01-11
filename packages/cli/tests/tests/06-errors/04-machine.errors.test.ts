import { expect, test } from '@playwright/test';
import { SYSTEM_DEFAULTS } from '@rediacc/shared/config';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { ErrorPatterns, expectError, nonExistentName } from '../../src/utils/errors';

/**
 * Negative test cases for machine commands.
 */
test.describe('Machine Error Scenarios @cli @errors', () => {
  let runner: CliTestRunner;
  let defaultTeamName: string;
  let defaultBridgeName: string;

  test.beforeAll(async () => {
    runner = CliTestRunner.fromGlobalState();

    // Get default team
    const teamsResult = await runner.teamList();
    const teams = runner.expectSuccessArray<{ teamName: string }>(teamsResult);
    defaultTeamName =
      teams.find((t) => t.teamName !== 'Private Team')?.teamName ?? SYSTEM_DEFAULTS.TEAM_NAME;

    // Get default region
    const regionsResult = await runner.run(['region', 'list']);
    const regions = runner.expectSuccessArray<{ regionName: string }>(regionsResult);
    const defaultRegionName = regions[0].regionName;

    // Get first available bridge from the default region
    const bridgesResult = await runner.run(['bridge', 'list', '--region', defaultRegionName]);
    const bridges = runner.expectSuccessArray<{ bridgeName: string }>(bridgesResult);
    if (bridges.length === 0) {
      throw new Error('No bridges available for machine tests');
    }
    defaultBridgeName = bridges[0].bridgeName;
  });

  test.describe('CreateMachine errors', () => {
    test('should fail when creating machine with duplicate name', async () => {
      const machineName = `error-test-dup-${Date.now()}`;

      // Create the machine first
      const createResult = await runner.machineCreate(
        machineName,
        defaultTeamName,
        defaultBridgeName
      );
      expect(createResult.success, `Setup failed: ${runner.getErrorMessage(createResult)}`).toBe(
        true
      );

      try {
        // Try to create with same name - should fail
        const duplicateResult = await runner.machineCreate(
          machineName,
          defaultTeamName,
          defaultBridgeName
        );
        expectError(runner, duplicateResult, {
          messageContains: ErrorPatterns.MACHINE_ALREADY_EXISTS,
        });
      } finally {
        // Cleanup
        await runner.machineDelete(machineName, defaultTeamName);
      }
    });

    test('should fail when creating machine in non-existent team', async () => {
      const result = await runner.run([
        'machine',
        'create',
        'test-machine',
        '--team',
        nonExistentName('team'),
        '--bridge',
        defaultBridgeName,
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });
  });

  test.describe('DeleteMachine errors', () => {
    test('should fail when deleting non-existent machine', async () => {
      const result = await runner.run([
        'machine',
        'delete',
        nonExistentName('machine'),
        '--team',
        defaultTeamName,
        '--force',
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.MACHINE_NOT_FOUND });
    });

    test('should fail when deleting machine from non-existent team', async () => {
      const result = await runner.run([
        'machine',
        'delete',
        'some-machine',
        '--team',
        nonExistentName('team'),
        '--force',
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });
  });

  test.describe('RenameMachine errors', () => {
    test('should fail when renaming non-existent machine', async () => {
      const result = await runner.run([
        'machine',
        'rename',
        nonExistentName('machine'),
        'new-name',
        '--team',
        defaultTeamName,
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.MACHINE_NOT_FOUND });
    });

    test('should fail when renaming machine from non-existent team', async () => {
      const result = await runner.run([
        'machine',
        'rename',
        'some-machine',
        'new-name',
        '--team',
        nonExistentName('team'),
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });

    test('should fail when renaming to an existing machine name', async () => {
      const tempMachine1 = `error-test-rename1-${Date.now()}`;
      const tempMachine2 = `error-test-rename2-${Date.now()}`;

      // Create two machines
      const create1Result = await runner.machineCreate(
        tempMachine1,
        defaultTeamName,
        defaultBridgeName
      );
      expect(create1Result.success, `Setup failed: ${runner.getErrorMessage(create1Result)}`).toBe(
        true
      );

      const create2Result = await runner.machineCreate(
        tempMachine2,
        defaultTeamName,
        defaultBridgeName
      );
      expect(create2Result.success, `Setup failed: ${runner.getErrorMessage(create2Result)}`).toBe(
        true
      );

      try {
        // Try to rename machine1 to machine2's name - should fail
        const renameResult = await runner.run([
          'machine',
          'rename',
          tempMachine1,
          tempMachine2,
          '--team',
          defaultTeamName,
        ]);
        expectError(runner, renameResult, { messageContains: 'already exists in team' });
      } finally {
        // Cleanup
        await runner.machineDelete(tempMachine1, defaultTeamName);
        await runner.machineDelete(tempMachine2, defaultTeamName);
      }
    });
  });

  test.describe('AssignBridge errors', () => {
    test('should fail when assigning bridge to non-existent machine', async () => {
      const result = await runner.run([
        'machine',
        'assign-bridge',
        nonExistentName('machine'),
        defaultBridgeName,
        '--team',
        defaultTeamName,
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.MACHINE_NOT_FOUND });
    });

    test('should fail when assigning machine from non-existent team', async () => {
      const result = await runner.run([
        'machine',
        'assign-bridge',
        'some-machine',
        defaultBridgeName,
        '--team',
        nonExistentName('team'),
      ]);
      expectError(runner, result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });
  });

  test.describe('RenameMachine empty name errors', () => {
    test('should fail when renaming machine to empty name', async () => {
      const tempMachineName = `error-test-empty-${Date.now()}`;

      // Create a temp machine
      const createResult = await runner.machineCreate(
        tempMachineName,
        defaultTeamName,
        defaultBridgeName
      );
      expect(createResult.success, `Setup failed: ${runner.getErrorMessage(createResult)}`).toBe(
        true
      );

      try {
        // Try to rename to empty string - should fail
        const renameResult = await runner.run([
          'machine',
          'rename',
          tempMachineName,
          '',
          '--team',
          defaultTeamName,
        ]);
        expectError(runner, renameResult, { messageContains: ErrorPatterns.MACHINE_NAME_EMPTY });
      } finally {
        // Cleanup
        await runner.machineDelete(tempMachineName, defaultTeamName);
      }
    });
  });
});
