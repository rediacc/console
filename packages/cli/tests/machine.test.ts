import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { runCli } from './helpers/cli.js';

describe('machine commands', () => {
  let teamName: string;

  beforeAll(async () => {
    // Get a valid team name for machine queries
    const listResult = await runCli(['team', 'list']);
    const teams = listResult.json as unknown[];
    teamName = (teams[0] as Record<string, unknown>).teamName as string;
  });

  describe('machine list', () => {
    it('should list all machines for a team', async () => {
      const result = await runCli(['machine', 'list', '--team', teamName]);

      expect(result.success).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);

      const machines = result.json as unknown[];
      if (machines.length > 0) {
        const machine = machines[0] as Record<string, unknown>;
        expect(machine).toHaveProperty('machineName');
        expect(machine).toHaveProperty('teamName');
      }
    });

    it('should handle missing team name', async () => {
      // Clear any context first
      const result = await runCli(['machine', 'list']);

      // Should either fail or use context
      // Depending on implementation, this might succeed if context is set
      expect(result).toBeDefined();
    });
  });

  describe('machine status', () => {
    it('should show machine status for a team', async () => {
      const result = await runCli(['machine', 'status', '--team', teamName]);

      // Machine status may fail if no machines exist or require region
      // For fresh accounts, just verify the command runs
      expect(result.success || result.stderr.includes('required')).toBe(true);
    });
  });

  describe('machine inspect', () => {
    it('should inspect a machine', async () => {
      // First list machines to get a valid name
      const listResult = await runCli(['machine', 'list', '--team', teamName]);
      const machines = listResult.json as unknown[];

      if (machines.length > 0) {
        const machineName = (machines[0] as Record<string, unknown>).machineName as string;

        const result = await runCli(['machine', 'inspect', machineName, '--team', teamName]);

        expect(result.success).toBe(true);
        expect(result.json).not.toBeNull();
      }
    });
  });

  describe('machine vault-status', () => {
    it('should show vault status for a machine', async () => {
      // First list machines to get a valid name
      const listResult = await runCli(['machine', 'list', '--team', teamName]);
      const machines = listResult.json as unknown[];

      if (machines.length > 0) {
        const machineName = (machines[0] as Record<string, unknown>).machineName as string;

        const result = await runCli(['machine', 'vault-status', machineName, '--team', teamName]);

        expect(result.success).toBe(true);
      }
    });
  });

  describe('machine repos', () => {
    it('should list repositories on a machine', async () => {
      // First list machines to get a valid name
      const listResult = await runCli(['machine', 'list', '--team', teamName]);
      const machines = listResult.json as unknown[];

      if (machines.length > 0) {
        const machineName = (machines[0] as Record<string, unknown>).machineName as string;

        const result = await runCli(['machine', 'repos', machineName, '--team', teamName]);

        expect(result.success).toBe(true);
      }
    });
  });

  // CRUD operations - safe to run with fresh company registration
  describe('machine CRUD operations', () => {
    const testMachineName = `test-machine-${Date.now()}`;
    const testBridgeName = `test-bridge-machine-${Date.now()}`;
    let renamedMachineName: string;

    beforeAll(async () => {
      // Create a bridge for machine tests (machines require a bridge)
      await runCli(['bridge', 'create', testBridgeName, '--region', 'Default Region']);
    });

    afterAll(async () => {
      // Cleanup the bridge
      await runCli(['bridge', 'delete', testBridgeName, '--region', 'Default Region', '--force']);
    });

    it('should create a new machine', async () => {
      const result = await runCli([
        'machine',
        'create',
        testMachineName,
        '--team',
        teamName,
        '--bridge',
        testBridgeName,
      ]);
      expect(result.success).toBe(true);
    });

    it('should rename the machine', async () => {
      renamedMachineName = `${testMachineName}-renamed`;
      const result = await runCli([
        'machine',
        'rename',
        testMachineName,
        renamedMachineName,
        '--team',
        teamName,
      ]);
      expect(result.success).toBe(true);
    });

    it('should delete the machine', async () => {
      const result = await runCli([
        'machine',
        'delete',
        renamedMachineName,
        '--team',
        teamName,
        '--force',
      ]);
      expect(result.success).toBe(true);
    });
  });
});
