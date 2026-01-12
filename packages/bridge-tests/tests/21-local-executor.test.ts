import { expect, test } from '@playwright/test';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

/**
 * Bridge Local Executor Tests
 *
 * Tests the Go executor functions that run locally.
 * Uses `renet bridge once --test-mode` which runs without API connection.
 *
 * Migrated from: ops/scripts/bridge.sh::bridge_test_local()
 */
test.describe('Bridge Local Executor @bridge', () => {
  let runner: BridgeTestRunner;

  // eslint-disable-next-line @typescript-eslint/require-await
  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test('machine_ping function should return pong', async () => {
    const result = await runner.testSimpleFunction('machine_ping');

    expect(result.code).toBe(0);
    // Output may be in stdout or stderr (log output)
    const output = (result.stdout + result.stderr).toLowerCase();
    expect(output).toContain('pong');
  });

  test('daemon_nop function should succeed silently', async () => {
    const result = await runner.testSimpleFunction('daemon_nop');

    expect(result.code).toBe(0);
    // daemon_nop should succeed with no output or minimal output
    expect(result.stderr).not.toContain('error');
  });

  test('machine_version function should return version info', async () => {
    const result = await runner.testSimpleFunction('machine_version');

    expect(result.code).toBe(0);
    // Output may be in stdout or stderr (log output)
    const output = (result.stdout + result.stderr).toLowerCase();
    expect(output).toMatch(/renet|version|\d+\.\d+/);
  });

  test('should reject unknown function', async () => {
    const result = await runner.testSimpleFunction('nonexistent_function_xyz');

    // Should fail with error about unknown function
    expect(result.code).not.toBe(0);
  });
});

/**
 * Renet Binary Tests
 *
 * Tests that verify renet binary is available and working.
 */
test.describe('Renet Binary @bridge @smoke', () => {
  let runner: BridgeTestRunner;

  // eslint-disable-next-line @typescript-eslint/require-await
  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test('renet binary should be available', async () => {
    const available = await runner.isRenetAvailable();
    expect(available).toBe(true);
  });

  test('renet version should return valid output', async () => {
    const result = await runner.getRenetVersion();

    expect(result.code).toBe(0);
    expect(result.stdout).toMatch(/renet|version/i);
  });
});
