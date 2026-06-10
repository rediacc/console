import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SFTPClient } from '@rediacc/shared-desktop/sftp';
import { downloadCertCache } from '../cert-cache.js';

const { mockLeaseExec, mockRelease, mockAcquire, mockConfigService } = vi.hoisted(() => {
  const mockLeaseExec = vi.fn();
  const sftp = { exec: mockLeaseExec, execStreaming: vi.fn().mockResolvedValue(0) };
  const mockRelease = vi.fn();
  const mockAcquire = vi.fn().mockResolvedValue({
    sftp,
    machine: { machineName: 'm1', ip: '127.0.0.1', user: 'root', port: 22 },
    sshPrivateKey: 'dummy-key',
    ensure: vi.fn().mockResolvedValue(sftp),
    release: mockRelease,
  });
  return {
    mockLeaseExec,
    mockRelease,
    mockAcquire,
    mockConfigService: {
      getLocalConfig: vi.fn(),
      getCurrent: vi.fn(),
      updateConfigFields: vi.fn(),
    },
  };
});

vi.mock('../machine-connection.js', () => ({
  machineConnections: { acquire: mockAcquire },
}));

vi.mock('../config-resources.js', () => ({
  configService: mockConfigService,
}));

const EMPTY_ACME = JSON.stringify({ letsencrypt: { Certificates: [] } });

describe('downloadCertCache connection sharing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockConfigService.getLocalConfig.mockResolvedValue({
      machines: {
        m1: { ip: '127.0.0.1', user: 'root', infra: { baseDomain: 'rediacc.io' } },
      },
    });
    mockConfigService.getCurrent.mockResolvedValue({});
    mockConfigService.updateConfigFields.mockResolvedValue(undefined);
    mockLeaseExec.mockResolvedValue(EMPTY_ACME);
  });

  it('reuses a caller-provided shared SFTP session without touching the pool', async () => {
    const exec = vi.fn().mockResolvedValue(EMPTY_ACME);
    const close = vi.fn();
    const sharedSftp = { exec, close } as unknown as SFTPClient;

    const result = await downloadCertCache('m1', { silent: true }, sharedSftp);

    expect(result).toEqual({ certCount: 0, compressedSize: expect.any(Number) });
    expect(mockAcquire).not.toHaveBeenCalled();
    expect(exec).toHaveBeenCalledWith('sudo cat /opt/rediacc/proxy/letsencrypt/acme.json');
    // The caller owns the shared connection; it must not be closed here.
    expect(close).not.toHaveBeenCalled();
    expect(mockConfigService.updateConfigFields).toHaveBeenCalledWith({
      acmeCertCache: expect.objectContaining({
        'rediacc.io': expect.objectContaining({ baseDomain: 'rediacc.io', sourceMachine: 'm1' }),
      }),
    });
  });

  it('acquires from the shared pool by default and releases when done', async () => {
    const result = await downloadCertCache('m1', { silent: true });

    expect(result).toEqual({ certCount: 0, compressedSize: expect.any(Number) });
    expect(mockAcquire).toHaveBeenCalledExactlyOnceWith('m1');
    expect(mockLeaseExec).toHaveBeenCalledWith('sudo cat /opt/rediacc/proxy/letsencrypt/acme.json');
    expect(mockRelease).toHaveBeenCalledTimes(1);
  });

  it('releases the lease even when the machine has no baseDomain', async () => {
    mockConfigService.getLocalConfig.mockResolvedValue({
      machines: { m1: { ip: '127.0.0.1', user: 'root' } },
    });

    const result = await downloadCertCache('m1', { silent: true });

    expect(result).toBeNull();
    expect(mockRelease).toHaveBeenCalledTimes(1);
  });

  it('throws a helpful error for unknown machines', async () => {
    await expect(downloadCertCache('nope', { silent: true })).rejects.toThrow(
      'Machine "nope" not found'
    );
    expect(mockAcquire).not.toHaveBeenCalled();
  });
});
