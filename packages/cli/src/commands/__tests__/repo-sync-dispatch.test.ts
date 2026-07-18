import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  mockSftpUploadFile,
  mockSftpUploadPaths,
  mockSftpDownloadFile,
  mockSftpDownloadDirectory,
  mockWithPooledSftp,
  pooledSftp,
} = vi.hoisted(() => {
  const pooledSftp = { marker: 'pooled-sftp' };
  return {
    pooledSftp,
    mockSftpUploadFile: vi.fn(() => Promise.resolve('upload-file-result')),
    mockSftpUploadPaths: vi.fn(() => Promise.resolve('upload-paths-result')),
    mockSftpDownloadFile: vi.fn(() => Promise.resolve('download-file-result')),
    mockSftpDownloadDirectory: vi.fn(() => Promise.resolve('download-dir-result')),
    // Stands in for the pool: hands the transfer a leased client and releases it.
    mockWithPooledSftp: vi.fn((_config: unknown, fn: (sftp: unknown) => unknown) => fn(pooledSftp)),
  };
});

vi.mock('../../remote/sync/index.js', async (orig) => {
  const real = await orig();
  return {
    ...real,
    sftpUploadFile: mockSftpUploadFile,
    sftpUploadPaths: mockSftpUploadPaths,
    sftpDownloadFile: mockSftpDownloadFile,
    sftpDownloadDirectory: mockSftpDownloadDirectory,
  };
});

vi.mock('../../services/machine/machine-connection.js', () => ({
  withPooledSftp: mockWithPooledSftp,
}));

import type { ConnectionDetails } from '../../services/machine/ssh-connection.js';
import {
  type SyncConnectionContext,
  sftpDownloadTransfer,
  sftpUploadTransfer,
} from '../repo-sync.js';

const details: ConnectionDetails = {
  host: '127.0.0.1',
  port: 22,
  user: 'tester',
  privateKey: 'KEY',
  known_hosts: '',
  universalUser: 'svc',
  workingDirectory: '/mnt/repo',
  datastore: '/mnt/rediacc',
};

const ctx: SyncConnectionContext = {
  details,
  remotePath: '/mnt/repo/sub',
  sftpRemotePath: 'sub/path.txt',
  sftpConfig: { host: '127.0.0.1', port: 22, username: 'tester', privateKey: 'KEY' },
};

beforeEach(() => {
  mockSftpUploadFile.mockClear();
  mockSftpUploadPaths.mockClear();
  mockSftpDownloadFile.mockClear();
  mockSftpDownloadDirectory.mockClear();
  mockWithPooledSftp.mockClear();
});

describe('sftpUploadTransfer', () => {
  const sources = [{ path: '/local/a.txt', isFile: true }];

  it('isFileMode=true → sftpUploadFile, never sftpUploadPaths', async () => {
    const result = await sftpUploadTransfer(true, sources, ctx, { dryRun: true });
    expect(result).toBe('upload-file-result');
    expect(mockSftpUploadFile).toHaveBeenCalledTimes(1);
    expect(mockSftpUploadFile).toHaveBeenCalledWith('/local/a.txt', 'sub/path.txt', pooledSftp, {
      dryRun: true,
    });
    expect(mockSftpUploadPaths).not.toHaveBeenCalled();
  });

  it('isFileMode=false → sftpUploadPaths, never sftpUploadFile', async () => {
    const dirSources = [{ path: '/local/dir', isFile: false }];
    const result = await sftpUploadTransfer(false, dirSources, ctx, { dryRun: true });
    expect(result).toBe('upload-paths-result');
    expect(mockSftpUploadPaths).toHaveBeenCalledTimes(1);
    expect(mockSftpUploadPaths).toHaveBeenCalledWith(dirSources, 'sub/path.txt', pooledSftp, {
      dryRun: true,
    });
    expect(mockSftpUploadFile).not.toHaveBeenCalled();
  });

  it('leases the connection from the pool with the resolved connect options', async () => {
    await sftpUploadTransfer(true, sources, ctx, { dryRun: true });
    expect(mockWithPooledSftp).toHaveBeenCalledTimes(1);
    expect(mockWithPooledSftp).toHaveBeenCalledWith(ctx.sftpConfig, expect.any(Function));
  });
});

describe('sftpDownloadTransfer', () => {
  it('isFileMode=true → sftpDownloadFile, never sftpDownloadDirectory', async () => {
    const result = await sftpDownloadTransfer(true, ctx, '/local', { dryRun: true });
    expect(result).toBe('download-file-result');
    expect(mockSftpDownloadFile).toHaveBeenCalledTimes(1);
    expect(mockSftpDownloadFile).toHaveBeenCalledWith('sub/path.txt', '/local', pooledSftp, {
      dryRun: true,
    });
    expect(mockSftpDownloadDirectory).not.toHaveBeenCalled();
  });

  it('isFileMode=false → sftpDownloadDirectory, never sftpDownloadFile', async () => {
    const result = await sftpDownloadTransfer(false, ctx, '/local', { dryRun: true });
    expect(result).toBe('download-dir-result');
    expect(mockSftpDownloadDirectory).toHaveBeenCalledTimes(1);
    expect(mockSftpDownloadDirectory).toHaveBeenCalledWith('sub/path.txt', '/local', pooledSftp, {
      dryRun: true,
    });
    expect(mockSftpDownloadFile).not.toHaveBeenCalled();
  });

  it('leases the connection from the pool with the resolved connect options', async () => {
    await sftpDownloadTransfer(false, ctx, '/local', { dryRun: true });
    expect(mockWithPooledSftp).toHaveBeenCalledTimes(1);
    expect(mockWithPooledSftp).toHaveBeenCalledWith(ctx.sftpConfig, expect.any(Function));
  });
});
