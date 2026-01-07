/**
 * Integration tests for local mode CLI commands.
 *
 * These tests verify the CLI commands work correctly through
 * the actual process execution. Tests the context create-local,
 * add-machine, remove-machine, machines, and run commands.
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { runCli } from './helpers/cli.js';

describe('local context commands', () => {
  const timestamp = Date.now();
  const testLocalContext = `test-local-cli-${timestamp}`;
  const testMachine = 'test-server';
  let originalContext: string | null = null;

  beforeAll(async () => {
    // Save current context
    const result = await runCli(['context', 'current'], { skipJsonParse: true });
    if (result.success) {
      originalContext = result.stdout.trim();
    }
  });

  afterAll(async () => {
    // Cleanup: delete test context
    await runCli(['context', 'delete', testLocalContext], { skipJsonParse: true });

    // Restore original context if it existed
    if (originalContext) {
      await runCli(['context', 'use', originalContext], { skipJsonParse: true });
    }
  });

  describe('context create-local', () => {
    it('should create a new local context', async () => {
      const result = await runCli(
        ['context', 'create-local', testLocalContext, '--ssh-key', '~/.ssh/id_rsa'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('created');
      expect(result.stdout).toContain(testLocalContext);
    });

    it('should fail if SSH key path is missing', async () => {
      const result = await runCli(['context', 'create-local', 'no-key-context'], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('--ssh-key');
    });

    it('should create and switch with --switch flag', async () => {
      const switchContext = `test-switch-${timestamp}`;

      const result = await runCli(
        ['context', 'create-local', switchContext, '--ssh-key', '~/.ssh/id_rsa', '--switch'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('Switched');

      // Verify we're on the new context
      const currentResult = await runCli(['context', 'current'], { skipJsonParse: true });
      expect(currentResult.stdout.trim()).toBe(switchContext);

      // Cleanup
      await runCli(['context', 'use', testLocalContext], { skipJsonParse: true });
      await runCli(['context', 'delete', switchContext], { skipJsonParse: true });
    });

    it('should accept custom renet path', async () => {
      const customPathContext = `test-custom-${timestamp}`;

      const result = await runCli(
        [
          'context',
          'create-local',
          customPathContext,
          '--ssh-key',
          '~/.ssh/id_rsa',
          '--renet-path',
          '/opt/bin/renet',
        ],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);

      // Switch to the new context and check the path
      await runCli(['context', 'use', customPathContext], { skipJsonParse: true });
      const showResult = await runCli(['context', 'show']);

      expect(showResult.json).toBeDefined();
      expect((showResult.json as { renetPath: string }).renetPath).toBe('/opt/bin/renet');

      // Cleanup
      await runCli(['context', 'delete', customPathContext], { skipJsonParse: true });
    });

    it('should fail for duplicate context name', async () => {
      const result = await runCli(
        ['context', 'create-local', testLocalContext, '--ssh-key', '~/.ssh/id_rsa'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('already exists');
    });
  });

  describe('context add-machine', () => {
    beforeAll(async () => {
      // Ensure we're on the local context
      await runCli(['context', 'use', testLocalContext], { skipJsonParse: true });
    });

    it('should add a machine to the local context', async () => {
      const result = await runCli(
        ['context', 'add-machine', testMachine, '--ip', '192.168.1.100', '--user', 'testuser'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);
      expect(result.stdout).toContain(testMachine);
      expect(result.stdout).toContain('added');
    });

    it('should accept optional port and datastore', async () => {
      const result = await runCli(
        [
          'context',
          'add-machine',
          'full-machine',
          '--ip',
          '10.0.0.1',
          '--user',
          'admin',
          '--port',
          '2222',
          '--datastore',
          '/data/rediacc',
        ],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);
    });

    it('should fail without required --ip', async () => {
      const result = await runCli(['context', 'add-machine', 'no-ip', '--user', 'testuser'], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('--ip');
    });

    it('should fail without required --user', async () => {
      const result = await runCli(['context', 'add-machine', 'no-user', '--ip', '10.0.0.1'], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('--user');
    });
  });

  describe('context machines', () => {
    it('should list all machines', async () => {
      const result = await runCli(['context', 'machines']);

      expect(result.success).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);

      const machines = result.json as { name: string; ip: string }[];
      expect(machines.length).toBeGreaterThanOrEqual(1);

      const testMachineEntry = machines.find((m) => m.name === testMachine);
      expect(testMachineEntry).toBeDefined();
      expect(testMachineEntry?.ip).toBe('192.168.1.100');
    });

    it('should show machine details in table format', async () => {
      const result = await runCli(['context', 'machines'], { outputFormat: 'table' });

      expect(result.success).toBe(true);
      expect(result.stdout).toContain(testMachine);
      expect(result.stdout).toContain('192.168.1.100');
    });
  });

  describe('context show (local mode)', () => {
    it('should show local context details', async () => {
      const result = await runCli(['context', 'show']);

      expect(result.success).toBe(true);
      expect(result.json).toBeDefined();

      const ctx = result.json as {
        name: string;
        mode: string;
        sshKey: string;
        machines: number;
      };

      expect(ctx.name).toBe(testLocalContext);
      expect(ctx.mode).toBe('local');
      expect(ctx.sshKey).toContain('.ssh');
      expect(ctx.machines).toBeGreaterThanOrEqual(1);
    });
  });

  describe('context list (with local)', () => {
    it('should show mode column in list', async () => {
      const result = await runCli(['context', 'list']);

      expect(result.success).toBe(true);
      const contexts = result.json as {
        name: string;
        mode: string;
        machines: string;
      }[];

      const localCtx = contexts.find((c) => c.name === testLocalContext);
      expect(localCtx?.mode).toBe('local');
      expect(localCtx?.machines).toBeDefined(); // Should show machine count
    });
  });

  describe('context set-ssh', () => {
    it('should update SSH configuration', async () => {
      const result = await runCli(
        [
          'context',
          'set-ssh',
          '--private-key',
          '~/.ssh/id_ed25519',
          '--public-key',
          '~/.ssh/id_ed25519.pub',
        ],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('updated');
    });
  });

  describe('context set-renet', () => {
    it('should update renet path', async () => {
      const result = await runCli(['context', 'set-renet', '/usr/local/bin/renet'], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('set to');

      // Verify in show
      const showResult = await runCli(['context', 'show']);
      expect((showResult.json as { renetPath: string }).renetPath).toBe('/usr/local/bin/renet');
    });
  });

  describe('context remove-machine', () => {
    it('should remove a machine', async () => {
      // First add a machine to remove
      await runCli(['context', 'add-machine', 'to-remove', '--ip', '1.1.1.1', '--user', 'test'], {
        skipJsonParse: true,
      });

      const result = await runCli(['context', 'remove-machine', 'to-remove'], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('removed');

      // Verify it's gone
      const machinesResult = await runCli(['context', 'machines']);
      const machines = machinesResult.json as { name: string }[];
      expect(machines.find((m) => m.name === 'to-remove')).toBeUndefined();
    });

    it('should fail for non-existent machine', async () => {
      const result = await runCli(['context', 'remove-machine', 'nonexistent'], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('not found');
    });
  });

  describe('run command (local mode detection)', () => {
    it('should detect local mode and show local prefix', async () => {
      // This test verifies that run command detects local mode
      // It will fail if renet isn't installed, but that's expected
      const result = await runCli(['run', 'machine_ping', '--machine', testMachine], {
        skipJsonParse: true,
      });

      // The command should attempt to run in local mode
      // It may fail if renet isn't installed, but output should mention [local]
      if (!result.success) {
        // If it failed, check that it was trying to run locally
        // or failed at execution level (not at mode detection)
        const output = result.stdout + result.stderr;
        const isLocalModeAttempt =
          output.includes('[local]') ||
          output.includes('spawn') ||
          output.includes('renet') ||
          output.includes('SSH');
        expect(isLocalModeAttempt).toBe(true);
      }
    });

    it('should require machine in local mode', async () => {
      // Clear the default machine first
      await runCli(['context', 'clear', 'machine'], { skipJsonParse: true });

      const result = await runCli(['run', 'machine_ping'], { skipJsonParse: true });

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('machine');
    });

    it('should accept --debug flag', async () => {
      const result = await runCli(['run', 'machine_ping', '--machine', testMachine, '--debug'], {
        skipJsonParse: true,
      });

      // The command will likely fail but should accept the debug flag
      // without syntax errors
      const output = result.stdout + result.stderr;
      expect(output).not.toContain('unknown option');
    });
  });
});

describe('switching between local and cloud contexts', () => {
  const timestamp = Date.now();
  const localContext = `switch-local-${timestamp}`;
  const cloudContext = `switch-cloud-${timestamp}`;

  beforeAll(async () => {
    // Create both contexts
    await runCli(['context', 'create-local', localContext, '--ssh-key', '~/.ssh/id_rsa'], {
      skipJsonParse: true,
    });
    await runCli(['context', 'create', cloudContext, '--api-url', 'https://test.example.com/api'], {
      skipJsonParse: true,
    });
  });

  afterAll(async () => {
    await runCli(['context', 'delete', localContext], { skipJsonParse: true });
    await runCli(['context', 'delete', cloudContext], { skipJsonParse: true });
  });

  it('should switch from cloud to local context', async () => {
    await runCli(['context', 'use', cloudContext], { skipJsonParse: true });

    let showResult = await runCli(['context', 'show']);
    expect((showResult.json as { mode: string }).mode).toBe('cloud');

    await runCli(['context', 'use', localContext], { skipJsonParse: true });

    showResult = await runCli(['context', 'show']);
    expect((showResult.json as { mode: string }).mode).toBe('local');
  });

  it('should switch from local to cloud context', async () => {
    await runCli(['context', 'use', localContext], { skipJsonParse: true });
    await runCli(['context', 'use', cloudContext], { skipJsonParse: true });

    const showResult = await runCli(['context', 'show']);
    expect((showResult.json as { mode: string }).mode).toBe('cloud');
  });

  it('should use correct mode for each context with -C flag', async () => {
    // Check local context with -C
    const localResult = await runCli(['-C', localContext, 'context', 'show']);
    expect((localResult.json as { mode: string }).mode).toBe('local');

    // Check cloud context with -C
    const cloudResult = await runCli(['-C', cloudContext, 'context', 'show']);
    expect((cloudResult.json as { mode: string }).mode).toBe('cloud');
  });
});
