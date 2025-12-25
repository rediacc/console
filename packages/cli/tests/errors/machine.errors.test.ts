import { describe, it, expect, beforeAll } from 'vitest';
import { runCli, getErrorMessage } from '../helpers/cli.js';
import { expectError, nonExistentName, ErrorPatterns } from '../helpers/errors.js';

/**
 * Negative test cases for machine commands.
 * Tests backend error responses from middleware stored procedures.
 */
describe('machine error scenarios', () => {
  let defaultTeamName: string;
  let defaultBridgeName: string;

  beforeAll(async () => {
    // Get default team and bridge for tests
    const teamsResult = await runCli(['team', 'list']);
    const teams = teamsResult.json as { teamName: string }[];
    defaultTeamName = teams.find((t) => t.teamName !== 'Private Team')?.teamName ?? 'Private Team';

    // Get default region
    const regionsResult = await runCli(['region', 'list']);
    const regions = regionsResult.json as { regionName: string }[];
    const defaultRegionName = regions[0].regionName;

    // Get first available bridge from the default region
    const bridgesResult = await runCli(['bridge', 'list', '--region', defaultRegionName]);
    const bridges = (bridgesResult.json ?? []) as { bridgeName: string }[];
    if (bridges.length === 0) {
      throw new Error('No bridges available for machine tests');
    }
    defaultBridgeName = bridges[0].bridgeName;
  });

  // ============================================
  // CreateMachine Errors
  // ============================================
  describe('CreateMachine errors', () => {
    it('should fail when creating machine with duplicate name', async () => {
      const machineName = `error-test-dup-${Date.now()}`;

      // Create the machine first
      const createResult = await runCli([
        'machine',
        'create',
        machineName,
        '--team',
        defaultTeamName,
        '--bridge',
        defaultBridgeName,
      ]);
      expect(createResult.success, `Setup failed: ${getErrorMessage(createResult)}`).toBe(true);

      try {
        // Try to create with same name - should fail
        const duplicateResult = await runCli([
          'machine',
          'create',
          machineName,
          '--team',
          defaultTeamName,
          '--bridge',
          defaultBridgeName,
        ]);
        expectError(duplicateResult, { messageContains: ErrorPatterns.MACHINE_ALREADY_EXISTS });
      } finally {
        // Cleanup
        await runCli(['machine', 'delete', machineName, '--team', defaultTeamName, '--force']);
      }
    });

    it('should fail when creating machine in non-existent team', async () => {
      const result = await runCli([
        'machine',
        'create',
        'test-machine',
        '--team',
        nonExistentName('team'),
        '--bridge',
        defaultBridgeName,
      ]);
      expectError(result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });
  });

  // ============================================
  // DeleteMachine Errors
  // ============================================
  describe('DeleteMachine errors', () => {
    it('should fail when deleting non-existent machine', async () => {
      const result = await runCli([
        'machine',
        'delete',
        nonExistentName('machine'),
        '--team',
        defaultTeamName,
        '--force',
      ]);
      expectError(result, { messageContains: ErrorPatterns.MACHINE_NOT_FOUND });
    });

    it('should fail when deleting machine from non-existent team', async () => {
      const result = await runCli([
        'machine',
        'delete',
        'some-machine',
        '--team',
        nonExistentName('team'),
        '--force',
      ]);
      expectError(result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });
  });

  // ============================================
  // RenameMachine Errors
  // ============================================
  describe('RenameMachine errors', () => {
    it('should fail when renaming non-existent machine', async () => {
      const result = await runCli([
        'machine',
        'rename',
        nonExistentName('machine'),
        'new-name',
        '--team',
        defaultTeamName,
      ]);
      expectError(result, { messageContains: ErrorPatterns.MACHINE_NOT_FOUND });
    });

    it('should fail when renaming machine from non-existent team', async () => {
      const result = await runCli([
        'machine',
        'rename',
        'some-machine',
        'new-name',
        '--team',
        nonExistentName('team'),
      ]);
      expectError(result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });

    it('should fail when renaming to an existing machine name', async () => {
      const tempMachine1 = `error-test-rename1-${Date.now()}`;
      const tempMachine2 = `error-test-rename2-${Date.now()}`;

      // Create two machines
      const create1Result = await runCli([
        'machine',
        'create',
        tempMachine1,
        '--team',
        defaultTeamName,
        '--bridge',
        defaultBridgeName,
      ]);
      expect(create1Result.success, `Setup failed: ${getErrorMessage(create1Result)}`).toBe(true);

      const create2Result = await runCli([
        'machine',
        'create',
        tempMachine2,
        '--team',
        defaultTeamName,
        '--bridge',
        defaultBridgeName,
      ]);
      expect(create2Result.success, `Setup failed: ${getErrorMessage(create2Result)}`).toBe(true);

      try {
        // Try to rename machine1 to machine2's name - should fail
        // Note: UpdateMachineName uses "already exists in team" while CreateMachine uses "already exists in your company"
        const renameResult = await runCli([
          'machine',
          'rename',
          tempMachine1,
          tempMachine2,
          '--team',
          defaultTeamName,
        ]);
        expectError(renameResult, { messageContains: 'already exists in team' });
      } finally {
        // Cleanup
        await runCli(['machine', 'delete', tempMachine1, '--team', defaultTeamName, '--force']);
        await runCli(['machine', 'delete', tempMachine2, '--team', defaultTeamName, '--force']);
      }
    });
  });

  // ============================================
  // AssignBridge Errors
  // ============================================
  describe('AssignBridge errors', () => {
    it('should fail when assigning bridge to non-existent machine', async () => {
      const result = await runCli([
        'machine',
        'assign-bridge',
        nonExistentName('machine'),
        defaultBridgeName,
        '--team',
        defaultTeamName,
      ]);
      expectError(result, { messageContains: ErrorPatterns.MACHINE_NOT_FOUND });
    });

    it('should fail when assigning machine from non-existent team', async () => {
      const result = await runCli([
        'machine',
        'assign-bridge',
        'some-machine',
        defaultBridgeName,
        '--team',
        nonExistentName('team'),
      ]);
      expectError(result, { messageContains: ErrorPatterns.TEAM_NOT_FOUND });
    });
  });
});
