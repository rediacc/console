import { expect, test } from '@playwright/test';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

/**
 * System Check Tests
 *
 * Tests for system check functions in renet functions.
 *
 * All functions are registered in GoExecutor (setup domain). This list is what
 * the DOMAIN contains, not a claim about what this file exercises, and the
 * difference used to matter more than it looks: check-e2e-coverage counted a
 * verb literal anywhere in a live suite, comments included, so naming
 * machine_uninstall here made it read as covered when nothing here calls it.
 * The gate strips comments now; the name is written split below so this line
 * cannot resurrect the claim.
 * - machine_ping, daemon_nop, machine_version, network_used, machine_ssh_test, setup,
 *   machine_(uninstall) -- NOT exercised here, see .e2e-coverage-allowlist
 * - machine_check_kernel, machine_check_setup, machine_check_memory
 * - machine_check_sudo, machine_check_tools, machine_check_renet, machine_check_criu
 * - machine_check_btrfs, machine_check_drivers, machine_check_system, machine_check_users
 * - machine_check_cli, machine_fix_groups, machine_converge_runtime (dry run)
 * Note: datastore_status is tested in 03-datastore-lifecycle.test.ts
 */

/**
 * OS images whose default boot leaves Landlock out of the active LSM list, so `renet sandbox-exec --detect` reports
 * NOT AVAILABLE and repo-key shells refuse there by design. Measured on the CI matrix (run 39640583259, 2026-10-21):
 * Oracle Linux 10 UEK 6.12 boots with `lsm=lockdown,capability,yama,selinux,bpf,ima,evm` and logs
 * "landlock: Disabled but requested by user space"; Ubuntu 24.04, Debian 13, Fedora 43 and openSUSE 16.0 report ABI 4-7.
 */
const LANDLOCK_INACTIVE_BY_DEFAULT = new Set(['ol-10']);

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

  test('network_used lists every network-ID claimant as a JSON array', async () => {
    const result = await runner.networkUsed();

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
    const output = runner.getCombinedOutput(result);
    expect(output).toMatch(/\[/);
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

  // Repo-key shells and transfers refuse to run without Landlock, so every supported OS leg must report it, except where the measured default boot leaves it out of `lsm=`. getCombinedOutput lowercases, so the patterns are lowercase; "status: not available" cannot match `status:\s*available`.
  test('sandbox-exec --detect reports Landlock as measured for this OS and records the ABI', async () => {
    // Read the file plainly and parse it here: a `$ID` in the remote command is expanded by the runner's own shell
    // before it reaches the VM (run 39658436875 printed `os=-`), so no shell variable may carry the answer.
    const release = runner.getCombinedOutput(await runner.executeOnWorker('cat /etc/os-release'));
    const field = (name: string) =>
      release.match(new RegExp(`^${name}="?([^"\\n]*)"?$`, 'm'))?.[1]?.trim() ?? '';
    const id = field('id');
    const major = field('version_id').split('.')[0];
    expect(
      id && major,
      `could not read the worker's OS from /etc/os-release: ${release}`
    ).toBeTruthy();
    const os = `${id}-${major}`;
    // The kernel's own list of active LSMs: Landlock is usable only when it is in it.
    const lsmRead = await runner.executeOnWorker('cat /sys/kernel/security/lsm');
    const lsm = runner.getCombinedOutput(lsmRead).trim();
    expect(lsmRead.code, `could not read /sys/kernel/security/lsm: ${lsm}`).toBe(0);
    const result = await runner.executeOnWorker('renet sandbox-exec --detect');
    const output = runner.getCombinedOutput(result);

    const abi = /landlock abi version:\s*(\d+)/.exec(output)?.[1] ?? 'unreported';
    test.info().annotations.push({
      type: 'landlock-abi',
      description: `ABI ${abi} on ${runner.getTargetVM()} (${os})`,
    });

    expect(result.code, output).toBe(0);
    // Detection must agree with the kernel on every OS: a detect that says NOT AVAILABLE while landlock is in the active LSM
    // list is a renet regression, and one that says AVAILABLE without it is a false pass.
    expect(lsm.split(',').includes('landlock'), `lsm=${lsm} vs detect: ${output}`).toBe(
      /status:\s*available/.test(output)
    );
    if (LANDLOCK_INACTIVE_BY_DEFAULT.has(os)) {
      // Repo-key shells refuse on this OS until Landlock is added to lsm= (PLAN-shell-sandbox-readonly-view E1). A pass here
      // after an image or kernel change means Landlock became active: move the OS out of the set.
      expect(
        output,
        `${os} now reports Landlock; remove it from LANDLOCK_INACTIVE_BY_DEFAULT`
      ).toMatch(/status:\s*not available/);
    } else {
      expect(output).toMatch(/status:\s*available/);
    }
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

  test('converge_runtime dry run should plan without restarting anything', async () => {
    const result = await runner.convergeRuntimeDryRun();

    expect(runner.isSuccess(result)).toBe(true);
    expect(result.code).toBe(0);
  });

  // NOTE: check_datastore is tested in 03-datastore-lifecycle.test.ts because it requires a datastore to be initialized first
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
