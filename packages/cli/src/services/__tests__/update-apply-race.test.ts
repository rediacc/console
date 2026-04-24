/**
 * Race-condition tests for the apply-then-update sequence on a single rdc
 * invocation. The bug these guard against was visible in production
 * (v1.0.7 release sequence on edge channel):
 *
 *   $ rdc update
 *   Updated to v1.0.7 (was v1.0.6). Changes take effect on next run.
 *   Checking for updates...
 *   Downloading v1.0.7...
 *   Downloading... 100%
 *   Updated from v1.0.6 to v1.0.7      <-- second apply!
 *
 * Two updates per invocation, both producing the same target version. The
 * second selfReplace renamed the freshly-applied v1.0.7 binary to .old, then
 * placed another v1.0.7 as current. Result: current and .old were the same
 * version, so `rdc update --rollback` silently no-op'd ("Rolled back
 * successfully" but `rdc --version` still reported v1.0.7).
 *
 * Root cause: applyPendingUpdate() at startup applies the staged binary, but
 * the in-memory VERSION constant is still the OLD version (it was baked into
 * the binary that was just replaced). The update command's "is there an
 * update?" check then compared stale in-memory VERSION to the manifest and
 * falsely decided another update was needed.
 *
 * Fix: applyPendingUpdate() now returns Promise<string | null> AND records
 * the applied version via _appliedAtStartup (module-level singleton).
 * handleUpdate() reads getAppliedAtStartup() before its check/download flow
 * and short-circuits when a startup apply already happened this invocation.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

describe('background-updater: applyPendingUpdate signal API', () => {
  beforeEach(async () => {
    const mod = await import('../background-updater.js');
    mod.resetAppliedAtStartupForTests();
  });

  afterEach(async () => {
    const mod = await import('../background-updater.js');
    mod.resetAppliedAtStartupForTests();
    vi.restoreAllMocks();
  });

  it('getAppliedAtStartup() returns null when nothing has been applied', async () => {
    const { getAppliedAtStartup } = await import('../background-updater.js');
    expect(getAppliedAtStartup()).toBeNull();
  });

  it('resetAppliedAtStartupForTests() clears the signal between tests', async () => {
    const { getAppliedAtStartup, resetAppliedAtStartupForTests } = await import(
      '../background-updater.js'
    );
    resetAppliedAtStartupForTests();
    expect(getAppliedAtStartup()).toBeNull();
  });
});

/**
 * Integration: drive the registered `update` Commander action and assert the
 * short-circuit fires. Mocks every module the command touches so the test is
 * fully in-process and offline.
 *
 * The critical invariant: when getAppliedAtStartup() returns a version,
 * checkForUpdate() and performUpdate() must NOT be called — otherwise we
 * regress to the duplicate-apply bug that corrupts .old.
 */
describe('handleUpdate short-circuit on appliedAtStartup', () => {
  let updaterMocks: {
    checkForUpdate: ReturnType<typeof vi.fn>;
    performUpdate: ReturnType<typeof vi.fn>;
    resolveChannel: ReturnType<typeof vi.fn>;
  };
  let bgMocks: {
    applyPendingUpdate: ReturnType<typeof vi.fn>;
    getAppliedAtStartup: ReturnType<typeof vi.fn>;
  };
  let outputMocks: {
    info: ReturnType<typeof vi.fn>;
    success: ReturnType<typeof vi.fn>;
    error: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    vi.resetModules();

    updaterMocks = {
      checkForUpdate: vi.fn().mockResolvedValue({ updateAvailable: true, latestVersion: '1.0.7' }),
      performUpdate: vi
        .fn()
        .mockResolvedValue({ success: true, fromVersion: '1.0.6', toVersion: '1.0.7' }),
      resolveChannel: vi.fn().mockReturnValue('edge'),
    };
    bgMocks = {
      applyPendingUpdate: vi.fn().mockResolvedValue(null),
      getAppliedAtStartup: vi.fn().mockReturnValue(null),
    };
    outputMocks = {
      info: vi.fn(),
      success: vi.fn(),
      error: vi.fn(),
    };

    vi.doMock('../updater.js', () => updaterMocks);
    vi.doMock('../background-updater.js', () => bgMocks);
    vi.doMock('../update-state.js', () => ({
      readUpdateState: vi.fn().mockResolvedValue({
        pendingUpdate: null,
        lastCheckAt: '2026-01-01T00:00:00.000Z',
      }),
      writeUpdateState: vi.fn().mockResolvedValue(undefined),
    }));
    vi.doMock('../output.js', () => ({ outputService: outputMocks }));
    vi.doMock('../subscription-auth.js', () => ({
      getSubscriptionServerUrl: vi.fn().mockReturnValue('https://example.invalid'),
    }));
    vi.doMock('../../i18n/index.js', () => ({
      t: (key: string, params?: Record<string, unknown>) =>
        params ? `${key}:${JSON.stringify(params)}` : key,
    }));
    vi.doMock('../../utils/platform.js', () => ({
      getInstallMethod: vi.fn().mockReturnValue('sea'),
      getNpmUpdateCommand: vi.fn().mockReturnValue('npm i -g @rediacc/cli'),
      getOldBinaryPath: vi.fn().mockReturnValue('/tmp/rdc.old'),
      isSEA: vi.fn().mockReturnValue(true),
    }));
    vi.doMock('../../utils/errors.js', () => ({ handleError: vi.fn() }));
    vi.doMock('../../version.js', () => ({ VERSION: '1.0.6' }));
  });

  afterEach(() => {
    vi.doUnmock('../updater.js');
    vi.doUnmock('../background-updater.js');
    vi.doUnmock('../update-state.js');
    vi.doUnmock('../output.js');
    vi.doUnmock('../subscription-auth.js');
    vi.doUnmock('../../i18n/index.js');
    vi.doUnmock('../../utils/platform.js');
    vi.doUnmock('../../utils/errors.js');
    vi.doUnmock('../../version.js');
  });

  async function runUpdateCommand(): Promise<void> {
    const { Command } = await import('commander');
    const { registerUpdateCommand } = await import('../../commands/update.js');
    const program = new Command();
    program.exitOverride(); // Commander would call process.exit otherwise
    registerUpdateCommand(program);
    await program.parseAsync(['node', 'rdc', 'update']);
  }

  it('does NOT call checkForUpdate / performUpdate when appliedAtStartup is set', async () => {
    bgMocks.getAppliedAtStartup.mockReturnValue('1.0.7');

    await runUpdateCommand();

    // Critical invariant: short-circuit fires before any check/download.
    expect(updaterMocks.checkForUpdate).not.toHaveBeenCalled();
    expect(updaterMocks.performUpdate).not.toHaveBeenCalled();
  });

  it('runs checkForUpdate when appliedAtStartup is null (normal path)', async () => {
    bgMocks.getAppliedAtStartup.mockReturnValue(null);

    await runUpdateCommand();

    expect(updaterMocks.checkForUpdate).toHaveBeenCalled();
  });

  it('does NOT print a redundant "Updated to ..." success message when short-circuiting', async () => {
    // The autoApplied message is printed by applyPendingUpdate to stderr at
    // startup; the update command must NOT additionally print success on the
    // same invocation when it short-circuits, which would be the duplicate
    // line the user observed in their terminal.
    bgMocks.getAppliedAtStartup.mockReturnValue('1.0.7');

    await runUpdateCommand();

    // No success message from the update command itself.
    expect(outputMocks.success).not.toHaveBeenCalled();
  });

  it('does not change behavior on --force (force still bypasses short-circuit)', async () => {
    bgMocks.getAppliedAtStartup.mockReturnValue('1.0.7');

    const { Command } = await import('commander');
    const { registerUpdateCommand } = await import('../../commands/update.js');
    const program = new Command();
    program.exitOverride();
    registerUpdateCommand(program);
    await program.parseAsync(['node', 'rdc', 'update', '--force']);

    // --force is the operator override; we do still run the check/download
    // flow even when an apply just happened.
    expect(updaterMocks.checkForUpdate).toHaveBeenCalled();
  });
});
