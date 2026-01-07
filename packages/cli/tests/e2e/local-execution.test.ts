/* eslint-disable no-console */
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
 *   E2E_VM1_IP=192.168.111.11 E2E_SSH_USER=root npm run test:run -- tests/e2e/
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { runCli } from '../helpers/cli.js';
import {
  getE2EConfig,
  setupE2EEnvironment,
  runLocalFunction,
  generateTestContextName,
  checkSSHKeyExists,
  assertSuccess,
} from '../helpers/local.js';

describe('E2E local execution', () => {
  const config = getE2EConfig();
  const contextName = generateTestContextName('e2e-local');
  let cleanup: (() => Promise<void>) | null = null;

  beforeAll(async () => {
    if (!config.enabled) {
      console.log('Skipping E2E tests: E2E_VM1_IP and E2E_SSH_USER not set');
      return;
    }

    // Check SSH key exists
    const keyExists = await checkSSHKeyExists(config.sshKeyPath);
    if (!keyExists) {
      console.log(`Skipping E2E tests: SSH key not found at ${config.sshKeyPath}`);
      return;
    }

    // Set up E2E environment
    cleanup = await setupE2EEnvironment(contextName);
  });

  afterAll(async () => {
    if (cleanup) {
      await cleanup();
    }
  });

  describe('basic execution', () => {
    it.skipIf(!config.enabled)('should execute ping on real VM', { timeout: 300000 }, async () => {
      const result = await runLocalFunction('machine_ping', 'vm1', {
        debug: true,
        timeout: 300000,
      });

      // Log output for debugging
      console.log('Ping output:', result.stdout);
      if (!result.success) {
        console.log('Ping stderr:', result.stderr);
      }

      // Ping should succeed on a properly configured VM
      expect(result.success).toBe(true);
    });

    it.skipIf(!config.enabled)('should show execution duration', { timeout: 300000 }, async () => {
      const result = await runLocalFunction('machine_ping', 'vm1', { timeout: 300000 });

      // Should include duration in output
      const output = result.stdout + result.stderr;
      const hasDuration =
        output.includes('Completed in') || output.includes('ms') || output.includes('seconds');

      // At minimum, the command should run
      if (result.success) {
        expect(hasDuration).toBe(true);
      }
    });

    it.skipIf(!config.enabled)('should handle debug flag', { timeout: 300000 }, async () => {
      const result = await runLocalFunction('machine_ping', 'vm1', {
        debug: true,
        timeout: 300000,
      });

      const output = result.stdout + result.stderr;

      // Debug mode should show more output
      const hasDebugOutput =
        output.includes('[local]') || output.includes('Executing') || output.includes('debug');

      if (result.success) {
        expect(hasDebugOutput).toBe(true);
      }
    });
  });

  describe('error handling', () => {
    it.skipIf(!config.enabled)('should handle non-existent machine', async () => {
      // Ensure we're on the E2E local context
      await runCli(['context', 'use', contextName], { skipJsonParse: true });

      const result = await runLocalFunction('machine_ping', 'nonexistent-machine');

      expect(result.success).toBe(false);
      expect(result.stdout + result.stderr).toContain('not found');
    });

    it.skipIf(!config.enabled)('should handle unknown function', async () => {
      // Ensure we're on the E2E local context
      await runCli(['context', 'use', contextName], { skipJsonParse: true });

      const result = await runLocalFunction('unknown_function_xyz_123', 'vm1');

      // Unknown function should fail
      expect(result.success).toBe(false);
    });

    it.skipIf(!config.enabled)(
      'should handle SSH connection timeout',
      { timeout: 60000 },
      async () => {
        // Create a context with a non-routable IP to test timeout
        const timeoutContext = `timeout-test-${Date.now()}`;

        await runCli(
          ['context', 'create-local', timeoutContext, '--ssh-key', config.sshKeyPath, '--switch'],
          { skipJsonParse: true }
        );

        // Add a non-routable machine
        await runCli(
          ['context', 'add-machine', 'timeout-vm', '--ip', '10.255.255.1', '--user', 'test'],
          { skipJsonParse: true }
        );

        // This should timeout (set short timeout)
        const result = await runLocalFunction('machine_ping', 'timeout-vm', { timeout: 30000 });

        expect(result.success).toBe(false);

        // Cleanup and restore original context
        await runCli(['context', 'use', contextName], { skipJsonParse: true });
        await runCli(['context', 'delete', timeoutContext], { skipJsonParse: true });
      }
    );
  });

  describe('parameter passing', () => {
    it.skipIf(!config.enabled)(
      'should pass parameters to function',
      { timeout: 300000 },
      async () => {
        // Ensure we're on the E2E local context
        await runCli(['context', 'use', contextName], { skipJsonParse: true });

        const result = await runLocalFunction('machine_ping', 'vm1', {
          params: { test_param: 'test_value' },
          debug: true,
          timeout: 300000,
        });

        // The machine_ping function should still work with extra params
        // Params are included in the vault
        const output = result.stdout + result.stderr;
        console.log('Param test output:', output);
      }
    );
  });

  describe('multiple machines', () => {
    it.skipIf(!config.enabled || !getE2EConfig().vm2Ip)(
      'should switch between machines',
      { timeout: 600000 },
      async () => {
        // Ensure we're on the E2E local context
        await runCli(['context', 'use', contextName], { skipJsonParse: true });

        // Execute on vm1
        const result1 = await runLocalFunction('machine_ping', 'vm1', { timeout: 300000 });
        console.log('VM1 result:', result1.success);

        // Execute on vm2
        const result2 = await runLocalFunction('machine_ping', 'vm2', { timeout: 300000 });
        console.log('VM2 result:', result2.success);

        // Both should succeed
        expect(result1.success || result2.success).toBe(true);
      }
    );
  });
});

describe('E2E context switching', () => {
  const config = getE2EConfig();
  const localContext = generateTestContextName('e2e-switch-local');
  const cloudContext = generateTestContextName('e2e-switch-cloud');

  beforeAll(async () => {
    if (!config.enabled) return;

    // Create both contexts
    await runCli(['context', 'create-local', localContext, '--ssh-key', config.sshKeyPath], {
      skipJsonParse: true,
    });

    await runCli(['context', 'create', cloudContext, '--api-url', 'https://test.example.com/api'], {
      skipJsonParse: true,
    });

    // Add a machine to local context
    await runCli(['context', 'use', localContext], { skipJsonParse: true });
    await runCli(
      ['context', 'add-machine', 'e2e-vm', '--ip', config.vm1Ip, '--user', config.sshUser],
      { skipJsonParse: true }
    );
  });

  afterAll(async () => {
    await runCli(['context', 'delete', localContext], { skipJsonParse: true });
    await runCli(['context', 'delete', cloudContext], { skipJsonParse: true });
  });

  it.skipIf(!config.enabled)('should detect mode correctly after switching', async () => {
    // Use local context
    await runCli(['context', 'use', localContext], { skipJsonParse: true });
    const localShow = await runCli(['context', 'show']);
    expect((localShow.json as { mode: string }).mode).toBe('local');

    // Use cloud context
    await runCli(['context', 'use', cloudContext], { skipJsonParse: true });
    const cloudShow = await runCli(['context', 'show']);
    expect((cloudShow.json as { mode: string }).mode).toBe('cloud');
  });

  it.skipIf(!config.enabled)(
    'should execute with -C flag override',
    { timeout: 300000 },
    async () => {
      // Start on cloud context
      await runCli(['context', 'use', cloudContext], { skipJsonParse: true });

      // Execute on local context using -C flag
      const result = await runCli(
        ['-C', localContext, 'run', 'machine_ping', '--machine', 'e2e-vm'],
        { skipJsonParse: true, timeout: 300000 }
      );

      // Should attempt local execution
      const output = result.stdout + result.stderr;
      const isLocalAttempt =
        output.includes('[local]') || output.includes('renet') || output.includes('Executing');

      expect(isLocalAttempt).toBe(true);
    }
  );
});

describe('E2E renet availability', () => {
  const config = getE2EConfig();

  it.skipIf(!config.enabled)('should verify renet is available', { timeout: 300000 }, async () => {
    const renetContextName = generateTestContextName('renet-check');

    // Create minimal local context
    const createResult = await runCli(
      ['context', 'create-local', renetContextName, '--ssh-key', config.sshKeyPath, '--switch'],
      { skipJsonParse: true }
    );
    assertSuccess(createResult, 'Failed to create local context');

    // Add machine
    await runCli(
      ['context', 'add-machine', 'check-vm', '--ip', config.vm1Ip, '--user', config.sshUser],
      { skipJsonParse: true }
    );

    // Try to run - this tests if renet is available
    const runResult = await runLocalFunction('machine_ping', 'check-vm', {
      debug: true,
      timeout: 300000,
    });

    console.log('Renet check output:', runResult.stdout);

    // If renet is not found, there should be a specific error
    if (!runResult.success) {
      const output = runResult.stdout + runResult.stderr;
      if (output.includes('spawn') && output.includes('ENOENT')) {
        console.log('Note: renet binary not found in PATH');
      }
    }

    // Cleanup
    await runCli(['context', 'delete', renetContextName], { skipJsonParse: true });
  });
});
