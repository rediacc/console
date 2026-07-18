import { expect, test } from '@playwright/test';
import { DEFAULT_DATASTORE_PATH } from '../src/constants';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

/**
 * Setup Command Tests
 *
 * Tests the setup function which:
 * 1. Uploads renet binary to worker VM via SFTP
 * 2. Installs renet from /tmp/renet-binary
 * 3. Runs renet setup to configure the machine
 *
 * These tests would have caught the bash -c syntax error that occurred
 * when the SetupCommand.Build() returned ["bash", "-c", "..."] which
 * was incorrectly joined into a command string.
 *
 * Migrated from: ops/scripts/workers.sh::worker_setup()
 */
test.describe('Setup Command @bridge', () => {
  let runner: BridgeTestRunner;

  // eslint-disable-next-line @typescript-eslint/require-await
  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test('setup command should not have shell syntax errors', async () => {
    // This test would have caught the bash -c error!
    // When setup was incorrectly using ["bash", "-c", "if..."], the
    // command would fail with: "syntax error near unexpected token `then'"
    const result = await runner.testFunction({
      function: 'setup',
      datastorePath: DEFAULT_DATASTORE_PATH,
    });

    // Check for common shell syntax errors
    expect(result.stderr).not.toContain('syntax error');
    expect(result.stderr).not.toContain('unexpected token');

    // The command should either succeed or fail gracefully
    // (it may fail in test-mode due to missing vault data, but not syntax errors)
  });

  test('setup command should handle compound shell commands', async () => {
    // The setup command uses: if [ -f /tmp/renet-binary ]; then ... fi && sudo renet setup
    // This tests that compound commands are properly formed

    const result = await runner.testFunction({
      function: 'setup',
      datastorePath: DEFAULT_DATASTORE_PATH,
    });

    // Should not have bash parsing errors
    expect(result.stderr).not.toMatch(/bash:.*syntax/i);
    expect(result.stderr).not.toMatch(/bash:.*unexpected/i);
  });
});

/**
 * Setup Command Edge Cases
 *
 * Tests for edge cases and error handling in the setup command.
 */
test.describe('Setup Command Edge Cases @bridge', () => {
  let runner: BridgeTestRunner;

  // eslint-disable-next-line @typescript-eslint/require-await
  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test('setup with missing datastore-path should handle gracefully', async () => {
    const result = await runner.testFunction({
      function: 'setup',
      // Note: no datastorePath provided
    });

    // Should either use default path or provide clear error
    // Should NOT have shell syntax errors
    expect(result.stderr).not.toContain('syntax error');
    expect(result.stderr).not.toContain('unexpected token');
  });

  test('setup alias should also work without syntax errors', async () => {
    // os_setup was an alias for setup (now both use setup)
    const result = await runner.testFunction({
      function: 'setup',
      datastorePath: DEFAULT_DATASTORE_PATH,
    });

    expect(result.stderr).not.toContain('syntax error');
    expect(result.stderr).not.toContain('unexpected token');
  });
});
