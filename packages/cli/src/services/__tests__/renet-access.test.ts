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

// An absolute path that exists, so resolveRenetPath never falls back to `which`.
const CONFIG = { renetPath: process.execPath };
const MACHINE = { ip: '10.0.0.5', user: 'root', port: 22 };

function inspectResult(overrides: Record<string, unknown> = {}) {
  return {
    arch: 'amd64',
    remotePath: '/usr/lib/rediacc/renet/1.2.3/renet',
    remoteHash: 'aaaaaaaaaaaaaaaaaaaa',
    remoteVersion: '1.2.3',
    localHash: 'bbbbbbbbbbbbbbbbbbbb',
    localVersion: '1.2.4',
    drift: 'version',
    ...overrides,
  };
}

function load() {
  return import('../renet/renet-execution.js');
}

describe('acquireRemoteRenet', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    delete process.env.REDIACC_ALLOW_DIRTY_RENET;
    delete process.env.REDIACC_SKIP_ROUTER_RESTART;
    mockProvision.mockResolvedValue({
      success: true,
      action: 'verified',
      arch: 'amd64',
      remotePath: '/usr/lib/rediacc/renet/1.2.4/renet',
    });
  });

  it("'read-only' inspects and never provisions", async () => {
    mockInspect.mockResolvedValue(inspectResult({ drift: 'none' }));
    const { acquireRemoteRenet } = await load();

    const result = await acquireRemoteRenet('read-only', CONFIG, MACHINE, 'key', {
      machineName: 'prod-1',
    });

    expect(mockInspect).toHaveBeenCalledTimes(1);
    expect(mockProvision).not.toHaveBeenCalled();
    expect(result).toEqual({
      remotePath: '/usr/lib/rediacc/renet/1.2.3/renet',
      uploaded: false,
      drift: 'none',
    });
    expect(mockWarn).not.toHaveBeenCalled();
  });

  it('warns once per host on drift, naming the machine, both versions and the fix', async () => {
    mockInspect.mockResolvedValue(inspectResult());
    const { acquireRemoteRenet } = await load();

    await acquireRemoteRenet('read-only', CONFIG, MACHINE, 'key', { machineName: 'prod-1' });
    await acquireRemoteRenet('read-only', CONFIG, MACHINE, 'key', { machineName: 'prod-1' });

    expect(mockWarn).toHaveBeenCalledTimes(1);
    const text = String(mockWarn.mock.calls[0][0]);
    expect(text).toContain('prod-1');
    expect(text).toContain('1.2.3');
    expect(text).toContain('1.2.4');
    expect(text).toContain('rdc machine setup prod-1');
    expect(mockProvision).not.toHaveBeenCalled();
  });

  it('rejects with the setup hint when the machine has no renet', async () => {
    mockInspect.mockResolvedValue(
      inspectResult({ drift: 'missing', remotePath: null, remoteHash: null, remoteVersion: null })
    );
    const { acquireRemoteRenet } = await load();

    await expect(
      acquireRemoteRenet('read-only', CONFIG, MACHINE, 'key', { machineName: 'fresh-vm' })
    ).rejects.toThrow('rdc machine setup fresh-vm');
    expect(mockProvision).not.toHaveBeenCalled();
  });

  it('the read-only path never spawns git', async () => {
    mockInspect.mockResolvedValue(inspectResult());
    const { acquireRemoteRenet } = await load();

    await acquireRemoteRenet('read-only', CONFIG, MACHINE, 'key', {});

    expect(mockExecFileSync).not.toHaveBeenCalled();
  });

  it("'provision' provisions with a router restart and an upload guard", async () => {
    const { acquireRemoteRenet } = await load();

    const result = await acquireRemoteRenet('provision', CONFIG, MACHINE, 'key', {});

    expect(mockInspect).not.toHaveBeenCalled();
    expect(mockProvision).toHaveBeenCalledTimes(1);
    const options = mockProvision.mock.calls[0][1] as {
      restartServices: boolean;
      uploadGuard?: () => void;
    };
    expect(options.restartServices).toBe(true);
    expect(typeof options.uploadGuard).toBe('function');
    expect(result.drift).toBeNull();
  });

  it('the upload guard refuses a dirty renet tree and names the opt-in', async () => {
    mockExecFileSync.mockImplementation((_cmd: string, args: string[]) =>
      args.includes('rev-parse') ? '/src/renet\n' : ' M pkg/list.go\n?? pkg/new.go\n'
    );
    const { acquireRemoteRenet } = await load();
    await acquireRemoteRenet('provision', CONFIG, MACHINE, 'key', {});
    const { uploadGuard } = mockProvision.mock.calls[0][1] as { uploadGuard: () => void };

    expect(() => uploadGuard()).toThrow(/REDIACC_ALLOW_DIRTY_RENET/);
    expect(() => uploadGuard()).toThrow(/pkg\/new\.go/);
    expect(() => uploadGuard()).toThrow(/10\.0\.0\.5/);

    process.env.REDIACC_ALLOW_DIRTY_RENET = '1';
    expect(() => uploadGuard()).not.toThrow();
  });

  it('the upload guard passes a clean tree and a binary outside any git tree', async () => {
    const { assertRenetSourceClean } = await load();

    mockExecFileSync.mockImplementation((_cmd: string, args: string[]) =>
      args.includes('rev-parse') ? '/src/renet\n' : ''
    );
    expect(() => assertRenetSourceClean('/src/renet/bin/renet', MACHINE)).not.toThrow();

    mockExecFileSync.mockImplementation(() => {
      throw new Error('not a git repository');
    });
    expect(() => assertRenetSourceClean('/usr/local/bin/renet', MACHINE)).not.toThrow();
  });
});
