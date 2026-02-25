import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import {
  checkSSHKeyExists,
  generateTestContextName,
  getE2EConfig,
  setupE2EEnvironment,
} from '../../src/utils/local';
import { SSHValidator } from '../../src/utils/SSHValidator';

/**
 * End-to-end tests for infrastructure configuration.
 *
 * Tests the full flow: set-infra -> show-infra -> push-infra
 * Verifies that config files are correctly generated on remote machines.
 *
 * Requires real OPS VMs:
 *   E2E_VM1_IP=192.168.111.11
 *   E2E_SSH_USER=root
 *   E2E_SSH_KEY=~/.ssh/id_rsa
 *
 * Run with:
 *   E2E_VM1_IP=192.168.111.11 E2E_SSH_USER=root npm test -- --project=e2e
 */
test.describe('E2E Infrastructure Config @cli @e2e', () => {
  const config = getE2EConfig();
  const contextName = generateTestContextName('e2e-infra');
  let cleanup: (() => Promise<void>) | null = null;
  let runner: CliTestRunner;
  let ssh: SSHValidator;

  // Remote file paths to clean up
  const remoteFiles = [
    '/opt/rediacc/proxy/config.env',
    '/opt/rediacc/proxy/docker-compose.override.yml',
    '/etc/rediacc/router.env',
  ];

  test.beforeAll(async () => {
    if (!config.enabled) {
      console.warn('Skipping E2E infra tests: E2E_VM1_IP and E2E_SSH_USER not set');
      return;
    }

    const keyExists = await checkSSHKeyExists(config.sshKeyPath);
    if (!keyExists) {
      console.warn(`Skipping E2E infra tests: SSH key not found at ${config.sshKeyPath}`);
      return;
    }

    cleanup = await setupE2EEnvironment(contextName);
    runner = CliTestRunner.withContext(contextName);
    ssh = new SSHValidator(config.vm1Ip, config.sshUser, config.sshKeyPath);
  });

  test.afterAll(async () => {
    // Clean up remote files
    if (config.enabled && ssh) {
      for (const file of remoteFiles) {
        await ssh.exec(`rm -f ${file}`).catch(() => {});
      }
    }

    if (cleanup) {
      await cleanup();
    }
  });

  test.describe('Set Infra Config', () => {
    test('should set infrastructure config for a machine', async () => {
      test.skip(!config.enabled, 'E2E not configured');

      const result = await runner.run([
        'config',
        'set-infra',
        'vm1',
        '--public-ipv4',
        config.vm1Ip,
        '--base-domain',
        'test.rediacc.local',
        '--cert-email',
        'test@test.com',
        '--tcp-ports',
        '8025,8143',
        '--udp-ports',
        '53',
      ]);

      expect(result.success, `set-infra failed: ${result.stdout}\n${result.stderr}`).toBe(true);
    });

    test('should show infrastructure config', async () => {
      test.skip(!config.enabled, 'E2E not configured');

      const result = await runner.run(['config', 'show-infra', 'vm1']);

      expect(result.success, `show-infra failed: ${result.stderr}`).toBe(true);

      const output = result.stdout;
      expect(output).toContain(config.vm1Ip);
      expect(output).toContain('test.rediacc.local');
      expect(output).toContain('test@test.com');
    });

    test('should merge infra config on update', async () => {
      test.skip(!config.enabled, 'E2E not configured');

      // Update only baseDomain
      const updateResult = await runner.run([
        'config',
        'set-infra',
        'vm1',
        '--base-domain',
        'updated.local',
      ]);
      expect(updateResult.success, `set-infra update failed: ${updateResult.stderr}`).toBe(true);

      // Verify previous values are preserved
      const showResult = await runner.run(['config', 'show-infra', 'vm1']);
      expect(showResult.success).toBe(true);

      const output = showResult.stdout;
      // baseDomain should be updated
      expect(output).toContain('updated.local');
      // publicIPv4 should still be preserved from the first set-infra
      expect(output).toContain(config.vm1Ip);
      // certEmail should still be preserved
      expect(output).toContain('test@test.com');
    });

    test('should warn when no options provided', async () => {
      test.skip(!config.enabled, 'E2E not configured');

      const result = await runner.run(['config', 'set-infra', 'vm1']);
      // Should not fail, but warn
      const output = result.stdout + result.stderr;
      expect(output).toContain('No options');
    });
  });

  test.describe('Push Infra Config', () => {
    test('should push infra config to remote machine', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(300_000);

      // Set infra config with test values before push
      await runner.run([
        'config',
        'set-infra',
        'vm1',
        '--public-ipv4',
        config.vm1Ip,
        '--base-domain',
        'test.rediacc.local',
        '--cert-email',
        'test@test.com',
        '--tcp-ports',
        '8025,8143',
        '--udp-ports',
        '53',
      ]);

      const result = await runner.run(['config', 'push-infra', 'vm1', '--debug'], {
        timeout: 300_000,
      });

      expect(
        result.success,
        `push-infra failed (exit ${result.exitCode}).\nstdout: ${result.stdout}\nstderr: ${result.stderr}`
      ).toBe(true);
    });

    test('should generate config.env on remote', async () => {
      test.skip(!config.enabled, 'E2E not configured');

      const exists = await ssh.fileExists('/opt/rediacc/proxy/config.env');
      expect(exists).toBe(true);

      const content = await ssh.readFile('/opt/rediacc/proxy/config.env');
      expect(content).toContain('BASE_DOMAIN="test.rediacc.local"');
      expect(content).toContain('CERTBOT_EMAIL="test@test.com"');
    });

    test('should generate router.env on remote', async () => {
      test.skip(!config.enabled, 'E2E not configured');

      const exists = await ssh.fileExists('/etc/rediacc/router.env');
      expect(exists).toBe(true);

      const content = await ssh.readFile('/etc/rediacc/router.env');
      expect(content).toContain('BASE_DOMAIN="test.rediacc.local"');
      expect(content).toContain('PORT="7111"');
    });

    test('should generate docker-compose.override.yml on remote', async () => {
      test.skip(!config.enabled, 'E2E not configured');

      const exists = await ssh.fileExists('/opt/rediacc/proxy/docker-compose.override.yml');
      expect(exists).toBe(true);

      const content = await ssh.readFile('/opt/rediacc/proxy/docker-compose.override.yml');
      // Should have IP-bound entrypoints
      expect(content).toContain(`${config.vm1Ip}:80`);
      expect(content).toContain(`${config.vm1Ip}:443`);
      // Should have ACME config
      expect(content).toContain('letsencrypt');
      expect(content).toContain('test@test.com');
      // Should have machine-specific TCP ports bound to IP
      expect(content).toContain(`${config.vm1Ip}:8025`);
      expect(content).toContain(`${config.vm1Ip}:8143`);
      // Should have encoded character flags
      expect(content).toContain('allowEncodedSlash=true');
      expect(content).toContain('allowEncodedQuestionMark=true');
    });

    test('should be idempotent', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(300_000);

      // Get checksums before second push
      const before = await ssh.exec(
        'sha256sum /opt/rediacc/proxy/config.env /etc/rediacc/router.env /opt/rediacc/proxy/docker-compose.override.yml 2>/dev/null'
      );

      // Push again
      const result = await runner.run(['config', 'push-infra', 'vm1'], { timeout: 300_000 });
      expect(result.success).toBe(true);

      // Get checksums after second push
      const after = await ssh.exec(
        'sha256sum /opt/rediacc/proxy/config.env /etc/rediacc/router.env /opt/rediacc/proxy/docker-compose.override.yml 2>/dev/null'
      );

      expect(after.stdout).toBe(before.stdout);
    });
  });

  test.describe('Partial Config', () => {
    test('should handle partial infra config (only baseDomain)', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(300_000);

      // Create a new context with minimal infra
      const partialContext = generateTestContextName('e2e-infra-partial');
      const partialRunner = new CliTestRunner();

      await partialRunner.run(['config', 'init', partialContext, '--ssh-key', config.sshKeyPath]);

      const ctxRunner = CliTestRunner.withContext(partialContext);
      await ctxRunner.run([
        'config',
        'add-machine',
        'vm1',
        '--ip',
        config.vm1Ip,
        '--user',
        config.sshUser,
      ]);

      // Set only baseDomain
      await ctxRunner.run(['config', 'set-infra', 'vm1', '--base-domain', 'partial.local']);

      // Push should succeed with partial config
      const result = await ctxRunner.run(['config', 'push-infra', 'vm1'], { timeout: 300_000 });

      expect(result.success, `Partial push failed: ${result.stderr}`).toBe(true);

      // config.env should have the baseDomain with default email
      const content = await ssh.readFile('/opt/rediacc/proxy/config.env');
      expect(content).toContain('BASE_DOMAIN="partial.local"');

      // Cleanup
      for (const file of remoteFiles) {
        await ssh.exec(`rm -f ${file}`).catch(() => {});
      }
      await partialRunner.run(['config', 'delete', partialContext]);
    });
  });
});
