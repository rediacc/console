import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  buildListCommand,
  fetchMachineStatus,
  fetchRepoLicenseDetail,
} from '../machine/machine-status.js';

const { mockExecStreaming, mockRelease, mockAcquire, mockConfigService, mockAcquireRenet } =
  vi.hoisted(() => {
    const mockExecStreaming = vi.fn();
    const sftp = { execStreaming: mockExecStreaming };
    const mockRelease = vi.fn();
    const mockAcquire = vi.fn().mockResolvedValue({
      sftp,
      machine: { machineName: 'm1', ip: '127.0.0.1', user: 'root', port: 22 },
      sshPrivateKey: 'dummy-key',
      ensure: vi.fn().mockResolvedValue(sftp),
      release: mockRelease,
    });
    return {
      mockExecStreaming,
      mockRelease,
      mockAcquire,
      mockConfigService: { getLocalConfig: vi.fn() },
      mockAcquireRenet: vi
        .fn()
        .mockResolvedValue({ remotePath: '/usr/lib/rediacc/renet/current/renet' }),
    };
  });

vi.mock('../machine/machine-connection.js', () => ({
  machineConnections: { acquire: mockAcquire },
}));

vi.mock('../config/config-resources.js', () => ({
  configService: mockConfigService,
}));

vi.mock('../renet/renet-execution.js', () => ({
  acquireRemoteRenet: mockAcquireRenet,
}));

vi.mock('../executor/local-executor.js', () => ({
  buildRenetEnvPrefix: vi.fn().mockReturnValue(''),
}));

vi.mock('../telemetry/otlp-credentials.js', () => ({
  fetchOtlpCredentials: vi.fn().mockResolvedValue(null),
}));

vi.mock('../telemetry/telemetry.js', () => ({
  isTelemetryDisabled: vi.fn().mockReturnValue(true),
}));

describe('buildListCommand', () => {
  const base = {
    envPrefix: '',
    remoteRenetPath: '/usr/lib/rediacc/renet/current/renet',
    datastore: '/mnt/rediacc',
  };

  it('omits --sections when no filter is given', () => {
    expect(buildListCommand(base)).toBe(
      'sudo /usr/lib/rediacc/renet/current/renet list all --datastore /mnt/rediacc --json'
    );
  });

  it('propagates a caller-provided sections filter', () => {
    expect(buildListCommand({ ...base, sections: ['containers'] })).toBe(
      'sudo /usr/lib/rediacc/renet/current/renet list all --datastore /mnt/rediacc --json --sections containers'
    );
    expect(buildListCommand({ ...base, sections: ['system', 'repositories'] })).toBe(
      'sudo /usr/lib/rediacc/renet/current/renet list all --datastore /mnt/rediacc --json --sections system,repositories'
    );
  });

  it('treats an empty sections array as no filter', () => {
    expect(buildListCommand({ ...base, sections: [] })).not.toContain('--sections');
  });
});

describe('fetchMachineStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockConfigService.getLocalConfig.mockResolvedValue({
      machines: { m1: { ip: '127.0.0.1', user: 'root', port: 22 } },
    });
    mockExecStreaming.mockImplementation(
      (_cmd: string, opts: { onStdout?: (data: Buffer) => void }) => {
        opts.onStdout?.(Buffer.from(JSON.stringify({ containers: [] })));
        return Promise.resolve(0);
      }
    );
  });

  it('runs renet list over a pooled connection and releases the lease', async () => {
    const result = await fetchMachineStatus('m1');

    expect(result).toEqual({ containers: [] });
    expect(mockAcquire).toHaveBeenCalledExactlyOnceWith('m1');
    expect(mockRelease).toHaveBeenCalledTimes(1);
    // The renet check reuses the lease's team key instead of re-reading it.
    expect(mockAcquireRenet).toHaveBeenCalledWith(
      'read-only',
      expect.anything(),
      expect.anything(),
      'dummy-key',
      expect.anything()
    );
  });

  it('never provisions renet: machine status is read-only', async () => {
    await fetchMachineStatus('m1');

    expect(mockAcquireRenet).toHaveBeenCalledTimes(1);
    expect(mockAcquireRenet.mock.calls[0][0]).toBe('read-only');
  });

  it('passes the sections filter through to the renet invocation', async () => {
    await fetchMachineStatus('m1', { sections: ['containers'] });

    expect(mockExecStreaming).toHaveBeenCalledWith(
      expect.stringContaining('--sections containers'),
      expect.anything()
    );
  });

  it('releases the lease when renet exits non-zero', async () => {
    mockExecStreaming.mockResolvedValue(1);

    await expect(fetchMachineStatus('m1')).rejects.toThrow('renet list all failed');
    expect(mockRelease).toHaveBeenCalledTimes(1);
  });

  it('rejects unknown machines before acquiring a connection', async () => {
    await expect(fetchMachineStatus('nope')).rejects.toThrow('Machine "nope" not found');
    expect(mockAcquire).not.toHaveBeenCalled();
  });
});

describe('fetchRepoLicenseDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockConfigService.getLocalConfig.mockResolvedValue({
      machines: { m1: { ip: '127.0.0.1', user: 'root', port: 22 } },
    });
  });

  it('resolves renet read-only, never provisioning it', async () => {
    await fetchRepoLicenseDetail('m1');

    expect(mockAcquireRenet).toHaveBeenCalledTimes(1);
    expect(mockAcquireRenet.mock.calls[0][0]).toBe('read-only');
  });
});
