import { beforeEach, describe, expect, it, vi } from 'vitest';
import { VERSION } from '../../version.js';
import { compareVersions } from '../updater.js';

const readFileMock = vi.fn();
const writeFileMock = vi.fn();
const mkdirMock = vi.fn();
const mkdtempMock = vi.fn();
const rmMock = vi.fn();
const computeSha256Mock = vi.fn();
const mockInstances: MockSFTPClient[] = [];
const connectDelegate = vi.fn(() => Promise.resolve());
const executeRsyncMock = vi.fn();
const getRsyncCommandMock = vi.fn();
const createTempSSHKeyFileMock = vi.fn();
const removeTempSSHKeyFileMock = vi.fn();

class MockSFTPClient {
  connect = vi.fn(() => connectDelegate());
  exec = vi.fn<(command: string) => Promise<string>>((command: string) => {
    if (command === 'uname -m') return 'x86_64\n';
    if (command.includes('flock -w 120')) return 'UPDATED CURRENT_UPDATED\n';
    if (command.includes(' version 2>/dev/null')) return 'remote-hash\n';
    if (command.includes('command -v rsync')) return '';
    if (command.startsWith('readlink ')) return '';
    if (command.includes('find ')) return '';
    if (command.includes('sha256sum')) return 'remote-hash\n';
    if (command.includes('systemctl is-active --quiet rediacc-router')) return 'RESTARTED\n';
    if (command.startsWith('rm -f ')) return '';
    throw new Error(`Unexpected command: ${command}`);
  });
  writeFile = vi.fn((_path: string, _data: Buffer) => Promise.resolve());
  exists = vi.fn((_path: string) => Promise.resolve(false));
  close = vi.fn();

  constructor(_config: unknown) {
    mockInstances.push(this);
  }
}

vi.mock('node:fs/promises', () => ({
  default: {
    readFile: readFileMock,
    writeFile: writeFileMock,
    mkdir: mkdirMock,
    mkdtemp: mkdtempMock,
    rm: rmMock,
  },
  readFile: readFileMock,
  writeFile: writeFileMock,
  mkdir: mkdirMock,
  mkdtemp: mkdtempMock,
  rm: rmMock,
}));

vi.mock('@rediacc/shared-desktop/sftp', () => ({
  SFTPClient: MockSFTPClient,
}));

vi.mock('../embedded-assets.js', () => ({
  isSEA: () => false,
  getEmbeddedRenetBinary: vi.fn(),
  computeSha256: computeSha256Mock,
}));

vi.mock('@rediacc/shared-desktop/sync', () => ({
  executeRsync: executeRsyncMock,
  getRsyncCommand: getRsyncCommandMock,
}));

vi.mock('@rediacc/shared-desktop/ssh', () => ({
  createTempSSHKeyFile: createTempSSHKeyFileMock,
  removeTempSSHKeyFile: removeTempSSHKeyFileMock,
}));

function parseVersionFromOutput(output: string): string | null {
  const match = /\d+\.\d+\.\d+/.exec(output);
  return match ? match[0] : null;
}

function wouldDowngrade(localVersion: string, remoteVersion: string): boolean {
  return compareVersions(localVersion, remoteVersion) < 0;
}

function shouldRestartServices(
  action: 'uploaded' | 'verified' | 'failed' | 'version_rejected',
  restartServices?: boolean
): boolean {
  return action === 'uploaded' && restartServices !== false;
}

const remoteInstallPath = `/usr/lib/rediacc/renet/${VERSION}/renet`;

function configureExec(
  instance: MockSFTPClient,
  options?: { remoteHash?: string; lockResult?: string }
) {
  const remoteHash = options?.remoteHash ?? 'remote-hash';
  const lockResult = options?.lockResult ?? 'UPDATED CURRENT_UPDATED\n';
  instance.exec.mockImplementation((command: string) => {
    if (command === 'uname -m') return 'x86_64\n';
    if (command.includes('flock -w 120')) return lockResult;
    if (command.includes(' version 2>/dev/null')) return `${remoteHash}\n`;
    if (command.includes('command -v rsync')) return '';
    if (command.startsWith('readlink ')) return '';
    if (command.includes('find ')) return '';
    if (command.includes('sha256sum')) return `${remoteHash}\n`;
    if (command.includes('systemctl is-active --quiet rediacc-router')) return 'RESTARTED\n';
    if (command.startsWith('rm -f ')) return '';
    throw new Error(`Unexpected command: ${command}`);
  });
}

function getMockInstance(index: number): MockSFTPClient {
  return mockInstances[index];
}

describe('renet version parsing', () => {
  it('should parse English output', () => {
    expect(parseVersionFromOutput('renet version 0.4.90')).toBe('0.4.90');
  });

  it('should parse English output with newline', () => {
    expect(parseVersionFromOutput('renet version 0.4.90\n')).toBe('0.4.90');
  });

  it('should parse Chinese output', () => {
    expect(parseVersionFromOutput('renet版本 0.4.90')).toBe('0.4.90');
  });

  it('should parse Turkish output', () => {
    expect(parseVersionFromOutput('renet sürümü 0.5.0')).toBe('0.5.0');
  });

  it('should parse German output', () => {
    expect(parseVersionFromOutput('renet Version 0.4.90')).toBe('0.4.90');
  });

  it('should parse Arabic output', () => {
    expect(parseVersionFromOutput('renet الإصدار 0.4.90')).toBe('0.4.90');
  });

  it('should parse Russian output', () => {
    expect(parseVersionFromOutput('renet версия 1.0.0')).toBe('1.0.0');
  });

  it('should parse Japanese output', () => {
    expect(parseVersionFromOutput('renet バージョン 0.4.90')).toBe('0.4.90');
  });

  it('should return null for garbage output', () => {
    expect(parseVersionFromOutput('garbage output')).toBeNull();
  });

  it('should return null for empty string', () => {
    expect(parseVersionFromOutput('')).toBeNull();
  });

  it('should return null for partial version', () => {
    expect(parseVersionFromOutput('renet version 0.4')).toBeNull();
  });
});

describe('downgrade detection', () => {
  it('should detect downgrade (remote newer)', () => {
    expect(wouldDowngrade('0.4.90', '0.5.0')).toBe(true);
  });

  it('should not flag upgrade (remote older)', () => {
    expect(wouldDowngrade('0.5.0', '0.4.90')).toBe(false);
  });

  it('should not flag same version', () => {
    expect(wouldDowngrade('0.4.90', '0.4.90')).toBe(false);
  });

  it('should detect major version downgrade', () => {
    expect(wouldDowngrade('0.4.90', '1.0.0')).toBe(true);
  });

  it('should detect patch-level downgrade', () => {
    expect(wouldDowngrade('0.4.89', '0.4.90')).toBe(true);
  });

  it('should not flag patch-level upgrade', () => {
    expect(wouldDowngrade('0.4.91', '0.4.90')).toBe(false);
  });
});

describe('service restart decision', () => {
  it('should restart after upload by default', () => {
    expect(shouldRestartServices('uploaded')).toBe(true);
  });

  it('should restart after upload when explicitly true', () => {
    expect(shouldRestartServices('uploaded', true)).toBe(true);
  });

  it('should not restart after upload when explicitly false', () => {
    expect(shouldRestartServices('uploaded', false)).toBe(false);
  });

  it('should not restart when binary was verified (no change)', () => {
    expect(shouldRestartServices('verified')).toBe(false);
  });

  it('should not restart on failure', () => {
    expect(shouldRestartServices('failed')).toBe(false);
  });

  it('should not restart on version rejected', () => {
    expect(shouldRestartServices('version_rejected')).toBe(false);
  });
});

describe('RenetProvisionerService', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    mockInstances.length = 0;
    connectDelegate.mockResolvedValue(undefined);
    readFileMock.mockResolvedValue(Buffer.from('renet-binary'));
    writeFileMock.mockResolvedValue(undefined);
    mkdirMock.mockResolvedValue(undefined);
    mkdtempMock.mockResolvedValue('/tmp/rdc-renet-local');
    rmMock.mockResolvedValue(undefined);
    computeSha256Mock.mockReturnValue('local-hash');
    executeRsyncMock.mockResolvedValue({
      success: true,
      filesTransferred: 1,
      bytesTransferred: 123,
      errors: [],
      duration: 10,
    });
    getRsyncCommandMock.mockResolvedValue('rsync');
    createTempSSHKeyFileMock.mockResolvedValue('/tmp/key');
    removeTempSSHKeyFileMock.mockResolvedValue(undefined);
  });

  it('coalesces concurrent provisioning calls for the same host', async () => {
    const { renetProvisioner } = await import('../renet-provisioner.js');
    const firstConnectGate = Promise.withResolvers<void>();
    let connectCalls = 0;
    connectDelegate.mockImplementation(async () => {
      connectCalls += 1;
      if (connectCalls === 1) {
        await firstConnectGate.promise;
      }
    });

    const provisionPromise1 = renetProvisioner.provision(
      { host: 'hostinger', username: 'muhammed', privateKey: 'key' },
      { localBinaryPath: '/tmp/renet' }
    );
    const provisionPromise2 = renetProvisioner.provision(
      { host: 'hostinger', username: 'muhammed', privateKey: 'key' },
      { localBinaryPath: '/tmp/renet' }
    );

    await vi.waitFor(() => expect(mockInstances).toHaveLength(1));
    configureExec(getMockInstance(0));
    firstConnectGate.resolve();

    const [result1, result2] = await Promise.all([provisionPromise1, provisionPromise2]);
    expect(result1.action).toBe('uploaded');
    expect(result2.action).toBe('uploaded');
    expect(result1.remotePath).toBe(remoteInstallPath);
    expect(mockInstances).toHaveLength(1);
    expect(getMockInstance(0).writeFile).toHaveBeenCalledTimes(1);
  });

  it('allows different hosts to provision in parallel with distinct staging paths', async () => {
    const { renetProvisioner } = await import('../renet-provisioner.js');
    const firstConnectGate = Promise.withResolvers<void>();
    const secondConnectGate = Promise.withResolvers<void>();
    let connectCalls = 0;
    connectDelegate.mockImplementation(async () => {
      connectCalls += 1;
      if (connectCalls === 1) {
        await firstConnectGate.promise;
        return;
      }
      await secondConnectGate.promise;
    });

    const promise1 = renetProvisioner.provision(
      { host: 'host-1', username: 'muhammed', privateKey: 'key' },
      { localBinaryPath: '/tmp/renet' }
    );
    const promise2 = renetProvisioner.provision(
      { host: 'host-2', username: 'muhammed', privateKey: 'key' },
      { localBinaryPath: '/tmp/renet' }
    );

    await vi.waitFor(() => expect(mockInstances).toHaveLength(2));
    configureExec(getMockInstance(0));
    configureExec(getMockInstance(1));
    firstConnectGate.resolve();
    secondConnectGate.resolve();

    const [result1, result2] = await Promise.all([promise1, promise2]);
    expect(result1.action).toBe('uploaded');
    expect(result2.action).toBe('uploaded');
    expect(result1.remotePath).toBe(remoteInstallPath);
    expect(result2.remotePath).toBe(remoteInstallPath);

    const stagingPath1 = String(getMockInstance(0).writeFile.mock.calls[0]?.[0] ?? '');
    const stagingPath2 = String(getMockInstance(1).writeFile.mock.calls[0]?.[0] ?? '');
    expect(stagingPath1).not.toBe(stagingPath2);
  });

  it('returns verified when the lock-holder recheck sees the binary already updated', async () => {
    const { renetProvisioner } = await import('../renet-provisioner.js');
    const connectGate = Promise.withResolvers<void>();
    connectDelegate.mockImplementation(async () => {
      await connectGate.promise;
    });
    const provisionPromise = renetProvisioner.provision(
      { host: 'hostinger', username: 'muhammed', privateKey: 'key' },
      { localBinaryPath: '/tmp/renet' }
    );

    await vi.waitFor(() => expect(mockInstances).toHaveLength(1));
    configureExec(getMockInstance(0), { lockResult: 'VERIFIED\n' });
    connectGate.resolve();

    const result = await provisionPromise;
    expect(result.action).toBe('verified');
    expect(result.remotePath).toBe(remoteInstallPath);
    expect(
      getMockInstance(0).exec.mock.calls.some(([command]) =>
        String(command).includes('systemctl is-active --quiet rediacc-router')
      )
    ).toBe(false);
  });

  it('uses delta sync from the current slot when rsync is available', async () => {
    const { renetProvisioner } = await import('../renet-provisioner.js');
    const connectGate = Promise.withResolvers<void>();
    connectDelegate.mockImplementation(async () => {
      await connectGate.promise;
    });
    const provisionPromise = renetProvisioner.provision(
      { host: 'hostinger', username: 'muhammed', privateKey: 'key' },
      { localBinaryPath: '/tmp/renet' }
    );

    await vi.waitFor(() => expect(mockInstances).toHaveLength(1));
    getMockInstance(0).exec.mockImplementation((command: string) => {
      if (command === 'uname -m') return 'x86_64\n';
      if (command.includes('flock -w 120')) return 'UPDATED CURRENT_UPDATED\n';
      if (command.includes(' version 2>/dev/null')) return 'remote-hash\n';
      if (command.includes('command -v rsync')) return '/usr/bin/rsync\n';
      if (command.startsWith('readlink ')) return '/usr/lib/rediacc/renet/0.5.9/renet\n';
      if (command.startsWith('cp -f ')) return '';
      if (command.includes('sha256sum')) return 'local-hash\n';
      throw new Error(`Unexpected command: ${command}`);
    });
    connectGate.resolve();

    const result = await provisionPromise;
    expect(result.success).toBe(true);
    expect(result.action).toBe('uploaded');
    expect(executeRsyncMock).toHaveBeenCalledTimes(1);
    expect(executeRsyncMock.mock.calls[0]?.[0]).toMatchObject({
      destination: expect.stringContaining('hostinger:/tmp/.rdc-staging-renet'),
      remoteRsyncPath: '/usr/bin/rsync',
    });
    expect(getMockInstance(0).writeFile).not.toHaveBeenCalled();
  });

  it('uses the current slot as delta seed even when it matches the target path', async () => {
    const { renetProvisioner } = await import('../renet-provisioner.js');
    const connectGate = Promise.withResolvers<void>();
    connectDelegate.mockImplementation(async () => {
      await connectGate.promise;
    });
    const provisionPromise = renetProvisioner.provision(
      { host: 'hostinger', username: 'muhammed', privateKey: 'key' },
      { localBinaryPath: '/tmp/renet' }
    );

    await vi.waitFor(() => expect(mockInstances).toHaveLength(1));
    getMockInstance(0).exec.mockImplementation((command: string) => {
      if (command === 'uname -m') return 'x86_64\n';
      if (command.includes('flock -w 120')) return 'UPDATED CURRENT_UPDATED\n';
      if (command.includes(' version 2>/dev/null')) return 'remote-hash\n';
      if (command.includes('command -v rsync')) return '/usr/bin/rsync\n';
      if (command.startsWith('readlink ')) return `${remoteInstallPath}\n`;
      if (command.startsWith('cp -f ')) return '';
      if (command.includes('sha256sum')) return 'local-hash\n';
      throw new Error(`Unexpected command: ${command}`);
    });
    connectGate.resolve();

    const result = await provisionPromise;
    expect(result.success).toBe(true);
    expect(result.action).toBe('uploaded');
    expect(executeRsyncMock).toHaveBeenCalledTimes(1);
    expect(getMockInstance(0).writeFile).not.toHaveBeenCalled();
  });

  it('updates current to the newly activated slot for mixed-version installs', async () => {
    const { renetProvisioner } = await import('../renet-provisioner.js');
    const remoteInstallPathNext = '/usr/lib/rediacc/renet/0.6.1/renet';
    const command = (
      renetProvisioner as unknown as {
        buildLockedInstallCommand: (
          stagingPath: string,
          localHash: string,
          remoteInstallPath: string
        ) => string;
      }
    ).buildLockedInstallCommand('/tmp/staging-renet', 'local-hash', remoteInstallPathNext);

    expect(command).toContain('/usr/lib/rediacc/renet/current/renet');
    expect(command).toContain('/usr/lib/rediacc/renet/0.6.1/renet');
    expect(command).toContain('/usr/lib/rediacc/renet/current/renet.tmp');
    expect(command).toContain('ln -sfn');
    expect(command).toContain('mv -Tf');
  });

  it('falls back to SFTP upload when delta sync is unavailable', async () => {
    getRsyncCommandMock.mockRejectedValue(new Error('rsync missing'));
    const { renetProvisioner } = await import('../renet-provisioner.js');
    const connectGate = Promise.withResolvers<void>();
    connectDelegate.mockImplementation(async () => {
      await connectGate.promise;
    });
    const provisionPromise = renetProvisioner.provision(
      { host: 'hostinger', username: 'muhammed', privateKey: 'key' },
      { localBinaryPath: '/tmp/renet' }
    );

    await vi.waitFor(() => expect(mockInstances).toHaveLength(1));
    getMockInstance(0).exec.mockImplementation((command: string) => {
      if (command === 'uname -m') return 'x86_64\n';
      if (command.includes('flock -w 120')) return 'UPDATED CURRENT_UPDATED\n';
      if (command.includes(' version 2>/dev/null')) return 'remote-hash\n';
      if (command.includes('command -v rsync')) return '/usr/bin/rsync\n';
      if (command.startsWith('readlink ')) return '/usr/lib/rediacc/renet/0.5.9/renet\n';
      throw new Error(`Unexpected command: ${command}`);
    });
    connectGate.resolve();

    const result = await provisionPromise;
    expect(result.success).toBe(true);
    expect(result.action).toBe('uploaded');
    expect(executeRsyncMock).not.toHaveBeenCalled();
    expect(getMockInstance(0).writeFile).toHaveBeenCalledTimes(1);
  });

  it('prefers embedded remote rsync when system rsync is missing', async () => {
    const { renetProvisioner } = await import('../renet-provisioner.js');
    const connectGate = Promise.withResolvers<void>();
    connectDelegate.mockImplementation(async () => {
      await connectGate.promise;
    });
    const provisionPromise = renetProvisioner.provision(
      { host: 'hostinger', username: 'muhammed', privateKey: 'key' },
      { localBinaryPath: '/tmp/renet' }
    );

    await vi.waitFor(() => expect(mockInstances).toHaveLength(1));
    getMockInstance(0).exec.mockImplementation((command: string) => {
      if (command === 'uname -m') return 'x86_64\n';
      if (command.includes('flock -w 120')) return 'UPDATED CURRENT_UPDATED\n';
      if (command.includes(' version 2>/dev/null')) return 'remote-hash\n';
      if (command.includes('command -v rsync')) return '/usr/local/bin/rsync-renet\n';
      if (command.startsWith('readlink ')) return '';
      if (command.includes('find ')) return '/usr/lib/rediacc/renet/0.5.8/renet\n';
      if (command.startsWith('cp -f ')) return '';
      if (command.includes('sha256sum')) return 'local-hash\n';
      throw new Error(`Unexpected command: ${command}`);
    });
    connectGate.resolve();

    const result = await provisionPromise;
    expect(result.success).toBe(true);
    expect(executeRsyncMock.mock.calls[0]?.[0]).toMatchObject({
      remoteRsyncPath: '/usr/local/bin/rsync-renet',
    });
  });

  it('surfaces a clear error when flock is unavailable remotely', async () => {
    const { renetProvisioner } = await import('../renet-provisioner.js');
    const connectGate = Promise.withResolvers<void>();
    connectDelegate.mockImplementation(async () => {
      await connectGate.promise;
    });
    const provisionPromise = renetProvisioner.provision(
      { host: 'hostinger', username: 'muhammed', privateKey: 'key' },
      { localBinaryPath: '/tmp/renet' }
    );

    await vi.waitFor(() => expect(mockInstances).toHaveLength(1));
    getMockInstance(0).exec.mockImplementation((command: string) => {
      if (command === 'uname -m') return 'x86_64\n';
      if (command.includes('flock -w 120'))
        throw new Error('Command exited with code 127: FLOCK_MISSING');
      if (command.includes(' version 2>/dev/null')) return 'remote-hash\n';
      if (command.includes('command -v rsync')) return '';
      if (command.startsWith('readlink ')) return '';
      if (command.includes('find ')) return '';
      if (command.startsWith('rm -f ')) return '';
      throw new Error(`Unexpected command: ${command}`);
    });
    connectGate.resolve();

    const result = await provisionPromise;
    expect(result.success).toBe(false);
    expect(result.error).toContain("missing 'flock'");
  });

  it('builds a lock command that is safe for POSIX sh', async () => {
    const { renetProvisioner } = await import('../renet-provisioner.js');
    const command = (
      renetProvisioner as unknown as {
        buildLockedInstallCommand: (
          stagingPath: string,
          localHash: string,
          remoteInstallPath: string
        ) => string;
      }
    ).buildLockedInstallCommand('/tmp/staging-renet', 'local-hash', remoteInstallPath);

    expect(command).toContain("flock -w 120 '/tmp/.rdc-renet-provision.lock' sh -c");
    expect(command).toContain("'set -eu;");
    expect(command).not.toContain('pipefail');
    expect(command).toContain('/usr/lib/rediacc/renet/current/renet');
  });

  it('marks verified when only the current pointer changes', async () => {
    const { renetProvisioner } = await import('../renet-provisioner.js');
    const connectGate = Promise.withResolvers<void>();
    connectDelegate.mockImplementation(async () => {
      await connectGate.promise;
    });
    const provisionPromise = renetProvisioner.provision(
      { host: 'hostinger', username: 'muhammed', privateKey: 'key' },
      { localBinaryPath: '/tmp/renet', restartServices: true }
    );

    await vi.waitFor(() => expect(mockInstances).toHaveLength(1));
    configureExec(getMockInstance(0), {
      remoteHash: 'local-hash',
      lockResult: 'CURRENT_UPDATED\n',
    });
    connectGate.resolve();

    const result = await provisionPromise;
    expect(result.action).toBe('verified');
    expect(result.servicesRestarted).toBe(true);
  });
});
