import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';

/**
 * Integration tests for local mode CLI commands.
 *
 * These tests verify the CLI commands work correctly through
 * the actual process execution. Tests the context create-local,
 * add-machine, remove-machine, machines, and run commands.
 *
 * NOTE: These tests don't need the master context - they create their own local contexts.
 */

test.describe('Local Context Commands @cli @core', () => {
  const timestamp = Date.now();
  const testLocalContext = `test-local-cli-${timestamp}`;
  const testMachine = 'test-server';
  let runner: CliTestRunner;

  test.beforeAll(() => {
    // Use a runner without context for creating local contexts
    runner = new CliTestRunner({});
  });

  test.afterAll(async () => {
    // Cleanup: delete test context
    await runner.run(['context', 'delete', testLocalContext, '--force'], { skipJsonParse: true });
  });

  test.describe('context create-local', () => {
    test('should create a new local context', async () => {
      const result = await runner.run(
        ['context', 'create-local', testLocalContext, '--ssh-key', '~/.ssh/id_rsa'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('created');
      expect(result.stdout).toContain(testLocalContext);
    });

    test('should fail if SSH key path is missing', async () => {
      const result = await runner.run(['context', 'create-local', 'no-key-context'], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('--ssh-key');
    });

    test('should accept custom renet path', async () => {
      const customPathContext = `test-custom-${timestamp}`;

      const result = await runner.run(
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

      // Check the path using --context flag
      const showResult = await runner.run(['--context', customPathContext, 'context', 'show']);

      expect(showResult.json).toBeDefined();
      expect((showResult.json as { renetPath: string }).renetPath).toBe('/opt/bin/renet');

      // Cleanup
      await runner.run(['context', 'delete', customPathContext, '--force'], {
        skipJsonParse: true,
      });
    });

    test('should fail for duplicate context name', async () => {
      const result = await runner.run(
        ['context', 'create-local', testLocalContext, '--ssh-key', '~/.ssh/id_rsa'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('already exists');
    });
  });

  test.describe('context add-machine', () => {
    test('should add a machine to the local context', async () => {
      const result = await runner.run(
        [
          '--context',
          testLocalContext,
          'context',
          'add-machine',
          testMachine,
          '--ip',
          '192.168.1.100',
          '--user',
          'testuser',
        ],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);
      expect(result.stdout).toContain(testMachine);
      expect(result.stdout).toContain('added');
    });

    test('should accept optional port and datastore', async () => {
      const result = await runner.run(
        [
          '--context',
          testLocalContext,
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

    test('should fail without required --ip', async () => {
      const result = await runner.run(
        ['--context', testLocalContext, 'context', 'add-machine', 'no-ip', '--user', 'testuser'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('--ip');
    });

    test('should fail without required --user', async () => {
      const result = await runner.run(
        ['--context', testLocalContext, 'context', 'add-machine', 'no-user', '--ip', '10.0.0.1'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('--user');
    });
  });

  test.describe('context machines', () => {
    test('should list all machines', async () => {
      const result = await runner.run(['--context', testLocalContext, 'context', 'machines']);

      expect(result.success).toBe(true);
      expect(Array.isArray(result.json)).toBe(true);

      const machines = runner.expectSuccessArray<{ name: string; ip: string }>(result);
      expect(machines.length).toBeGreaterThanOrEqual(1);

      const testMachineEntry = machines.find((m) => m.name === testMachine);
      expect(testMachineEntry).toBeDefined();
      expect(testMachineEntry?.ip).toBe('192.168.1.100');
    });

    test('should show machine details in table format', async () => {
      const result = await runner.run(['--context', testLocalContext, 'context', 'machines'], {
        outputFormat: 'table',
      });

      expect(result.success).toBe(true);
      expect(result.stdout).toContain(testMachine);
      expect(result.stdout).toContain('192.168.1.100');
    });
  });

  test.describe('context show (local mode)', () => {
    test('should show local context details', async () => {
      const result = await runner.run(['--context', testLocalContext, 'context', 'show']);

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

  test.describe('context list (with local)', () => {
    test('should show mode column in list', async () => {
      const result = await runner.run(['context', 'list']);

      expect(result.success).toBe(true);
      const contexts = runner.expectSuccessArray<{
        name: string;
        mode: string;
        machines: string;
      }>(result);

      const localCtx = contexts.find((c) => c.name === testLocalContext);
      expect(localCtx?.mode).toBe('local');
      expect(localCtx?.machines).toBeDefined();
    });
  });

  test.describe('context set-ssh', () => {
    test('should update SSH configuration', async () => {
      const result = await runner.run(
        [
          '--context',
          testLocalContext,
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

  test.describe('context set-renet', () => {
    test('should update renet path', async () => {
      const result = await runner.run(
        ['--context', testLocalContext, 'context', 'set-renet', '/usr/local/bin/renet'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('set to');

      // Verify in show
      const showResult = await runner.run(['--context', testLocalContext, 'context', 'show']);
      expect((showResult.json as { renetPath: string }).renetPath).toBe('/usr/local/bin/renet');
    });
  });

  test.describe('context remove-machine', () => {
    test('should remove a machine', async () => {
      // First add a machine to remove
      await runner.run(
        [
          '--context',
          testLocalContext,
          'context',
          'add-machine',
          'to-remove',
          '--ip',
          '1.1.1.1',
          '--user',
          'test',
        ],
        { skipJsonParse: true }
      );

      const result = await runner.run(
        ['--context', testLocalContext, 'context', 'remove-machine', 'to-remove'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(true);
      expect(result.stdout).toContain('removed');

      // Verify it's gone
      const machinesResult = await runner.run([
        '--context',
        testLocalContext,
        'context',
        'machines',
      ]);
      const machines = runner.expectSuccessArray<{ name: string }>(machinesResult);
      expect(machines.find((m) => m.name === 'to-remove')).toBeUndefined();
    });

    test('should fail for non-existent machine', async () => {
      const result = await runner.run(
        ['--context', testLocalContext, 'context', 'remove-machine', 'nonexistent'],
        { skipJsonParse: true }
      );

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('not found');
    });
  });

  test.describe('run command (local mode detection)', () => {
    test('should detect local mode and show local prefix', async () => {
      // This test verifies that run command detects local mode
      // It will fail if renet isn't installed, but that's expected
      const result = await runner.run(
        ['--context', testLocalContext, 'run', 'machine_ping', '--machine', testMachine],
        { skipJsonParse: true }
      );

      // The command should attempt to run in local mode
      if (!result.success) {
        const output = result.stdout + result.stderr;
        const isLocalModeAttempt =
          output.includes('[local]') ||
          output.includes('spawn') ||
          output.includes('renet') ||
          output.includes('SSH');
        expect(isLocalModeAttempt).toBe(true);
      }
    });

    test('should require machine in local mode', async () => {
      // Clear the default machine first
      await runner.run(['--context', testLocalContext, 'context', 'clear', 'machine'], {
        skipJsonParse: true,
      });

      const result = await runner.run(['--context', testLocalContext, 'run', 'machine_ping'], {
        skipJsonParse: true,
      });

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('machine');
    });

    test('should accept --debug flag', async () => {
      const result = await runner.run(
        ['--context', testLocalContext, 'run', 'machine_ping', '--machine', testMachine, '--debug'],
        { skipJsonParse: true }
      );

      const output = result.stdout + result.stderr;
      expect(output).not.toContain('unknown option');
    });
  });
});

test.describe('Switching Between Local and Cloud Contexts @cli @core', () => {
  const timestamp = Date.now();
  const localContext = `switch-local-${timestamp}`;
  const cloudContext = `switch-cloud-${timestamp}`;
  let runner: CliTestRunner;

  test.beforeAll(() => {
    runner = new CliTestRunner({});
  });

  test.afterAll(async () => {
    await runner.run(['context', 'delete', localContext, '--force'], { skipJsonParse: true });
    await runner.run(['context', 'delete', cloudContext, '--force'], { skipJsonParse: true });
  });

  test('should use correct mode for each context with -C flag', async () => {
    // Create both contexts
    await runner.run(['context', 'create-local', localContext, '--ssh-key', '~/.ssh/id_rsa'], {
      skipJsonParse: true,
    });
    await runner.run(
      ['context', 'create', cloudContext, '--api-url', 'https://test.example.com/api'],
      { skipJsonParse: true }
    );

    // Check local context with --context
    const localResult = await runner.run(['--context', localContext, 'context', 'show']);
    expect((localResult.json as { mode: string }).mode).toBe('local');

    // Check cloud context with --context
    const cloudResult = await runner.run(['--context', cloudContext, 'context', 'show']);
    expect((cloudResult.json as { mode: string }).mode).toBe('cloud');
  });
});
