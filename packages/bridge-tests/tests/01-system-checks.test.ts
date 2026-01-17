import { expect, test } from '@playwright/test';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

/**
 * System Check Tests
 *
 * Tests for system check functions in renet bridge.
 *
 * All functions are registered in GoExecutor (setup domain):
 * - machine_ping, daemon_nop, machine_version, machine_ssh_test, setup, machine_uninstall
 * - machine_check_kernel, machine_check_setup, machine_check_memory
 * - machine_check_sudo, machine_check_tools, machine_check_renet, machine_check_criu
 * - machine_check_btrfs, machine_check_drivers, machine_check_system, machine_check_users
 * - machine_check_cli, machine_fix_groups
 * Note: datastore_status is tested in 03-datastore-lifecycle.test.ts
 */
test.describe('System Functions @bridge @smoke', () => {
  let runner: BridgeTestRunner;

  test.beforeAll(() => {
    runner = BridgeTestRunner.forWorker();
  });

  // ===========================================================================
  // Implemented Functions
  // ===========================================================================

  test('ping should return pong', async () => {
    const result = await runner.ping();

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
    const output = runner.getCombinedOutput(result);
    expect(output).toContain('pong');
  });

  test('nop should succeed silently', async () => {
    const result = await runner.nop();

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('hello should return version info', async () => {
    const result = await runner.hello();

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
    const output = runner.getCombinedOutput(result);
    expect(output).toMatch(/renet|version|hello|\d+\.\d+/);
  });

  test('ssh_test should succeed', async () => {
    const result = await runner.sshTest();

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('check_kernel_compatibility should pass', async () => {
    const result = await runner.checkKernelCompatibility();

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('check_setup should report status', async () => {
    const result = await runner.checkSetup();

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('check_memory should report available memory', async () => {
    const result = await runner.checkMemory();

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('check_sudo should verify sudo access', async () => {
    const result = await runner.checkSudo();

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('check_tools should verify required tools', async () => {
    const result = await runner.checkTools();

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('check_renet should verify installation', async () => {
    const result = await runner.checkRenet();

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('check_criu should verify CRIU availability', async () => {
    const result = await runner.checkCriu();

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('check_btrfs should verify btrfs availability', async () => {
    const result = await runner.checkBtrfs();

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('check_drivers should verify drivers', async () => {
    const result = await runner.checkDrivers();

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('check_system should run all checks', async () => {
    const result = await runner.checkSystem();

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('check_users should verify user setup', async () => {
    const result = await runner.checkUsers();

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  test('check_rediacc_cli should verify CLI', async () => {
    const result = await runner.checkRediaccCli();

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  // NOTE: check_datastore is tested in 03-datastore-lifecycle.test.ts
  // because it requires a datastore to be initialized first
});

/**
 * Parallel Execution Tests
 */
test.describe('Parallel Execution @bridge', () => {
  let runner: BridgeTestRunner;

  test.beforeAll(() => {
    runner = BridgeTestRunner.forWorker();
  });

  test('implemented functions should run in parallel', async () => {
    const [pingResult, nopResult, helloResult] = await Promise.all([
      runner.ping(),
      runner.nop(),
      runner.hello(),
    ]);

    expect(runner.isSuccess(pingResult)).toBe(true);
    expect(runner.isSuccess(nopResult)).toBe(true);
    expect(runner.isSuccess(helloResult)).toBe(true);

    expect(pingResult.code).toBe(0);
    expect(nopResult.code).toBe(0);
    expect(helloResult.code).toBe(0);
  });
});

/**
 * Error Handling Tests
 */
test.describe('Error Handling @bridge', () => {
  let runner: BridgeTestRunner;

  test.beforeAll(() => {
    runner = BridgeTestRunner.forWorker();
  });

  test('unknown function should fail with clear error', async () => {
    const result = await runner.testSimpleFunction('nonexistent_function_xyz');

    expect(result.code).not.toBe(0);
    expect(runner.getErrorMessage(result)).toContain('unknown function');
  });
});
