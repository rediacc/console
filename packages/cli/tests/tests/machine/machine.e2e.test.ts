import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { E2E } from '../../src/utils/e2e-constants';
import { getE2EConfig, setupE2EEnvironment } from '../../src/utils/local';
import { SSHValidator } from '../../src/utils/SSHValidator';

/**
 * Phase 1: Machine Operations
 *
 * Tests machine_ping, machine_ssh_test, machine_version, machine_uninstall.
 * All operations take no params — they only need a machine target.
 *
 * machine_uninstall is tested last as it removes renet from the VM.
 * After uninstall, renet must be re-installed via setup before other phases.
 */
test.describe
  .serial('Phase 1: Machine Operations @e2e', () => {
    const config = getE2EConfig();
    let ssh1: SSHValidator;
    let cleanup: (() => Promise<void>) | null = null;
    let runner: CliTestRunner;
    const ctxName = `e2e-phase1-${Date.now()}`;

    test.beforeAll(async () => {
      test.skip(!config.enabled, 'E2E VMs not configured');
      ssh1 = new SSHValidator(config.vm1Ip, config.sshUser, config.sshKeyPath);
      cleanup = await setupE2EEnvironment(ctxName);
      runner = CliTestRunner.withContext(ctxName);
    });

    test.afterAll(async () => {
      // Re-install renet after the uninstall test so subsequent test files still work
      if (runner) {
        try {
          await runner.run(
            ['setup', '--machine', E2E.MACHINE_VM1],
            { timeout: E2E.SETUP_TIMEOUT }
          );
        } catch { /* best-effort */ }
      }
      await cleanup?.();
    });

    test('machine_ping - should ping VM successfully', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        ['run', 'machine_ping', '--machine', E2E.MACHINE_VM1],
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);
    });

    test('machine_ssh_test - should verify SSH connectivity', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        ['run', 'machine_ssh_test', '--machine', E2E.MACHINE_VM1],
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      // Also verify SSH independently
      const sshResult = await ssh1.exec('echo ok');
      expect(sshResult.success).toBe(true);
      expect(sshResult.stdout.trim()).toBe('ok');
    });

    test('machine_version - should return renet version', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runner.run(
        ['run', 'machine_version', '--machine', E2E.MACHINE_VM1],
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      // The output should contain a version string
      const output = result.stdout + result.stderr;
      expect(output.length).toBeGreaterThan(0);
    });

    test('machine_uninstall - should remove renet from VM', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.SETUP_TIMEOUT);

      const result = await runner.run(
        ['run', 'machine_uninstall', '--machine', E2E.MACHINE_VM1],
        { timeout: E2E.SETUP_TIMEOUT }
      );
      runner.expectSuccess(result);

      // SSH validation: renet binary should no longer exist at the system install path
      const checkResult = await ssh1.exec(
        'test -f /usr/bin/renet && echo EXISTS || echo NOT_FOUND'
      );
      expect(checkResult.stdout.trim()).toContain('NOT_FOUND');
    });
  });
