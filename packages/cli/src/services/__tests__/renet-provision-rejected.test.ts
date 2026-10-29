/**
 * renet-execution's half of a rejected upload: a `version_rejected` provision result becomes a thrown
 * message naming REDIACC_ALLOW_DOWNGRADE, never a success. The provisioner is mocked here; the
 * persisted-entry probe that leads to the rejection is pinned against the real provisioner in
 * renet-provision-remote-verify.test.ts.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockInspect, mockProvision, mockWarn, mockInfo, mockExecFileSync, mockExecSync } =
  vi.hoisted(() => ({
    mockInspect: vi.fn(),
    mockProvision: vi.fn(),
    mockWarn: vi.fn(),
    mockInfo: vi.fn(),
    mockExecFileSync: vi.fn(),
    mockExecSync: vi.fn(),
  }));

vi.mock('node:child_process', () => ({
  execFileSync: mockExecFileSync,
  execSync: mockExecSync,
}));

vi.mock('../renet/renet-provisioner.js', () => ({
  renetProvisioner: { inspect: mockInspect, provision: mockProvision },
}));

vi.mock('../core/output.js', () => ({
  outputService: { warn: mockWarn, info: mockInfo },
}));

vi.mock('../core/embedded-assets.js', () => ({
  isSEA: () => false,
}));

vi.mock('../machine/machine-connection.js', () => ({
  sftpConfigForMachine: vi.fn(() => ({ host: '10.0.0.5', username: 'root', privateKey: 'k' })),
  withSharedOrPooledSftp: vi.fn(),
}));

vi.mock('../renet/provision-state.js', () => ({
  isSetupVerifiedFresh: vi.fn(() => Promise.resolve(false)),
  recordSetupVerified: vi.fn(() => Promise.resolve()),
}));

const CONFIG = { renetPath: process.execPath };
const MACHINE = { ip: '10.0.0.5', user: 'root', port: 22 };

describe('acquireRemoteRenet with a rejected upload', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    delete process.env.REDIACC_ALLOW_DIRTY_RENET;
  });

  it('throws the downgrade guard message naming REDIACC_ALLOW_DOWNGRADE, never a success', async () => {
    mockProvision.mockResolvedValue({
      success: false,
      action: 'version_rejected',
      arch: 'amd64',
      remotePath: '/usr/lib/rediacc/renet/0.0.0-dev/renet',
      error:
        'Remote has renet v1.3.12 but this CLI bundles v0.0.0. Run `rdc update` to upgrade your CLI, or set REDIACC_ALLOW_DOWNGRADE=1 to force.',
    });
    const { acquireRemoteRenet } = await import('../renet/renet-execution.js');
    await expect(
      acquireRemoteRenet('provision', CONFIG, MACHINE, 'key', { machineName: 'm' })
    ).rejects.toThrow(/REDIACC_ALLOW_DOWNGRADE/);
  });
});
