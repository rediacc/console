import { beforeEach, describe, expect, it, vi } from 'vitest';
import { buildListCommand, fetchMachineStatus } from '../machine-status.js';

const { mockExecStreaming, mockRelease, mockAcquire, mockConfigService, mockProvision } =
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
      mockProvision: vi
        .fn()
        .mockResolvedValue({ remotePath: '/usr/lib/rediacc/renet/current/renet' }),
    };
  });

vi.mock('../machine-connection.js', () => ({
  machineConnections: { acquire: mockAcquire },
}));

vi.mock('../config-resources.js', () => ({
  configService: mockConfigService,
}));

vi.mock('../renet-execution.js', () => ({
  provisionRenetToRemote: mockProvision,
}));

vi.mock('../local-executor.js', () => ({
  buildRenetEnvPrefix: vi.fn().mockReturnValue(''),
}));

vi.mock('../otlp-credentials.js', () => ({
  fetchOtlpCredentials: vi.fn().mockResolvedValue(null),
}));

vi.mock('../telemetry.js', () => ({
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
    // Provisioning reuses the lease's team key instead of re-reading it.
    expect(mockProvision).toHaveBeenCalledWith(
      expect.anything(),
      expect.anything(),
      'dummy-key',
      expect.anything()
    );
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
