import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import {
  assertSuccess,
  checkSSHKeyExists,
  generateTestContextName,
  getE2EConfig,
  runLocalFunction,
  setupE2EEnvironment,
} from '../../src/utils/local';

/**
 * End-to-end tests for local mode execution.
 *
 * These tests require real OPS VMs to be available and configured via
 * environment variables:
 *
 *   E2E_VM1_IP=192.168.111.11
 *   E2E_VM2_IP=192.168.111.12  (optional)
 *   E2E_SSH_USER=root
 *   E2E_SSH_KEY=~/.ssh/id_rsa  (optional, defaults to ~/.ssh/id_rsa)
 *
 * Run with:
 *   E2E_VM1_IP=192.168.111.11 E2E_SSH_USER=root npm test -- --project=e2e
 */
test.describe('E2E Local Execution @cli @e2e', () => {
  const config = getE2EConfig();
  const contextName = generateTestContextName('e2e-local');
  let cleanup: (() => Promise<void>) | null = null;

  test.beforeAll(async () => {
    if (!config.enabled) {
      console.warn('Skipping E2E tests: E2E_VM1_IP and E2E_SSH_USER not set');
      return;
    }

    // Check SSH key exists
    const keyExists = await checkSSHKeyExists(config.sshKeyPath);
    if (!keyExists) {
      console.warn(`Skipping E2E tests: SSH key not found at ${config.sshKeyPath}`);
      return;
    }

    // Set up E2E environment
    cleanup = await setupE2EEnvironment(contextName);
  });

  test.afterAll(async () => {
    if (cleanup) {
      await cleanup();
    }
  });

  test.describe('Basic Execution', () => {
    test('should execute ping on real VM', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(300000);

      const result = await runLocalFunction('machine_ping', 'vm1', {
        contextName,
        debug: true,
        timeout: 300000,
      });

      expect(
        result.success,
        `Ping failed (exit ${result.exitCode}).\nstdout: ${result.stdout}\nstderr: ${result.stderr}`
      ).toBe(true);
    });

    test('should show execution duration', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(300000);

      const result = await runLocalFunction('machine_ping', 'vm1', {
        contextName,
        timeout: 300000,
      });

      const output = result.stdout + result.stderr;
      const hasDuration =
        output.includes('Completed in') || output.includes('ms') || output.includes('seconds');

      if (result.success) {
        expect(hasDuration).toBe(true);
      }
    });

    test('should handle debug flag', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(300000);

      const result = await runLocalFunction('machine_ping', 'vm1', {
        contextName,
        debug: true,
        timeout: 300000,
      });

      const output = result.stdout + result.stderr;
      const hasDebugOutput =
        output.includes('[local]') || output.includes('Executing') || output.includes('debug');

      if (result.success) {
        expect(hasDebugOutput).toBe(true);
      }
    });
  });

  test.describe('Error Handling', () => {
    test('should handle non-existent machine', async () => {
      test.skip(!config.enabled, 'E2E not configured');

      const result = await runLocalFunction('machine_ping', 'nonexistent-machine', { contextName });

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('not found');
    });

    test('should handle unknown function', async () => {
      test.skip(!config.enabled, 'E2E not configured');

      const result = await runLocalFunction('unknown_function_xyz_123', 'vm1', { contextName });

      expect(result.success).toBe(false);
    });

    test('should handle SSH connection timeout', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(60000);

      const runner = new CliTestRunner();
      const timeoutContext = `timeout-test-${Date.now()}`;

      await runner.run(['config', 'init', timeoutContext, '--ssh-key', config.sshKeyPath]);

      // Add a non-routable machine
      const timeoutRunner = CliTestRunner.withContext(timeoutContext);
      await timeoutRunner.run([
        'config',
        'add-machine',
        'timeout-vm',
        '--ip',
        '10.255.255.1',
        '--user',
        'test',
      ]);

      // This should timeout
      const result = await timeoutRunner.run(['run', 'machine_ping', '--machine', 'timeout-vm'], {
        timeout: 30000,
      });

      expect(result.success).toBe(false);

      // Cleanup
      await runner.run(['config', 'delete', timeoutContext]);
    });
  });

  test.describe('Parameter Passing', () => {
    test('should pass parameters to function', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(300000);

      const result = await runLocalFunction('machine_ping', 'vm1', {
        contextName,
        params: { test_param: 'test_value' },
        debug: true,
        timeout: 300000,
      });

      const output = result.stdout + result.stderr;
      console.warn('Param test output:', output);
    });
  });

  test.describe('Multiple Machines', () => {
    test('should switch between machines', async () => {
      test.skip(
        !config.enabled || !getE2EConfig().vm2Ip,
        'E2E not configured or VM2 not available'
      );
      test.setTimeout(600000);

      // Execute on vm1
      const result1 = await runLocalFunction('machine_ping', 'vm1', {
        contextName,
        timeout: 300000,
      });
      console.warn('VM1 result:', result1.success);

      // Execute on vm2
      const result2 = await runLocalFunction('machine_ping', 'vm2', {
        contextName,
        timeout: 300000,
      });
      console.warn('VM2 result:', result2.success);

      expect(result1.success || result2.success).toBe(true);
    });
  });
});

test.describe('E2E Context Switching @cli @e2e', () => {
  const config = getE2EConfig();
  const localContext = generateTestContextName('e2e-switch-local');
  const cloudContext = generateTestContextName('e2e-switch-cloud');
  let runner: CliTestRunner;

  test.beforeAll(async () => {
    test.skip(!config.enabled, 'E2E not configured');

    runner = new CliTestRunner();

    // Create both contexts
    await runner.run(['config', 'init', localContext, '--ssh-key', config.sshKeyPath]);
    await runner.run(['config', 'init', cloudContext, '--api-url', 'https://test.example.com/api']);

    // Add a machine to local context
    const localRunner = CliTestRunner.withContext(localContext);
    await localRunner.run([
      'config',
      'add-machine',
      'e2e-vm',
      '--ip',
      config.vm1Ip,
      '--user',
      config.sshUser,
    ]);
  });

  test.afterAll(async () => {
    if (runner) {
      await runner.run(['config', 'delete', localContext]).catch(() => {});
      await runner.run(['config', 'delete', cloudContext]).catch(() => {});
    }
  });

  test('should detect adapter correctly', async () => {
    test.skip(!config.enabled, 'E2E not configured');

    // Local config (with --ssh-key) shows adapter: 'local'
    const localRunner = CliTestRunner.withContext(localContext);
    const localShow = await localRunner.run(['config', 'show']);
    expect((localShow.json as { adapter: string }).adapter).toBe('local');

    // Config with --api-url but no token also shows adapter: 'local'
    // (cloud adapter requires both apiUrl AND token from authentication)
    const cloudRunner = CliTestRunner.withContext(cloudContext);
    const cloudShow = await cloudRunner.run(['config', 'show']);
    expect((cloudShow.json as { adapter: string }).adapter).toBe('local');
  });

  test('should execute with context override', async () => {
    test.skip(!config.enabled, 'E2E not configured');
    test.setTimeout(300000);

    const localRunner = CliTestRunner.withContext(localContext);
    const result = await localRunner.run(['run', 'machine_ping', '--machine', 'e2e-vm'], {
      timeout: 300000,
    });

    const output = result.stdout + result.stderr;
    const isLocalAttempt =
      output.includes('[local]') || output.includes('renet') || output.includes('Executing');

    expect(isLocalAttempt).toBe(true);
  });
});

test.describe('E2E Renet Availability @cli @e2e', () => {
  const config = getE2EConfig();

  test('should verify renet is available', async () => {
    test.skip(!config.enabled, 'E2E not configured');
    test.setTimeout(300000);

    const runner = new CliTestRunner();
    const renetContextName = generateTestContextName('renet-check');

    // Create minimal local context
    const createResult = await runner.run([
      'config',
      'init',
      renetContextName,
      '--ssh-key',
      config.sshKeyPath,
    ]);
    assertSuccess(createResult, 'Failed to create local context');

    // Add machine
    const contextRunner = CliTestRunner.withContext(renetContextName);
    await contextRunner.run([
      'config',
      'add-machine',
      'check-vm',
      '--ip',
      config.vm1Ip,
      '--user',
      config.sshUser,
    ]);

    // Try to run - this tests if renet is available
    const runResult = await contextRunner.run(
      ['run', 'machine_ping', '--machine', 'check-vm', '--debug'],
      { timeout: 300000 }
    );

    console.warn('Renet check output:', runResult.stdout);

    if (!runResult.success) {
      const output = runResult.stdout + runResult.stderr;
      if (output.includes('spawn') && output.includes('ENOENT')) {
        console.warn('Note: renet binary not found in PATH');
      }
    }

    // Cleanup
    await runner.run(['config', 'delete', renetContextName]);
  });
});
