import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MachineConfig } from '../../types/index.js';
import { refreshRepoLicensesBatch } from '../license.js';

const { mockExec, mockExecStreaming, mockConnect, mockClose, mockListRepositories } = vi.hoisted(
  () => ({
    mockExec: vi.fn(),
    mockExecStreaming: vi.fn(),
    mockConnect: vi.fn(),
    mockClose: vi.fn(),
    mockListRepositories: vi.fn(),
  })
);

vi.mock('@rediacc/shared-desktop/sftp', () => ({
  SFTPClient: class MockSFTPClient {
    connect = mockConnect;
    exec = mockExec;
    execStreaming = mockExecStreaming;
    close = mockClose;
  },
}));

vi.mock('node:fs/promises', () => ({
  readFile: vi.fn().mockResolvedValue('client-machine-001\n'),
}));

vi.mock('../subscription-auth.js', () => ({
  getSubscriptionTokenState: vi.fn(() => ({
    kind: 'ready',
    serverUrl: 'http://localhost:4800',
    token: { token: 'rdt_test' },
  })),
}));

vi.mock('../config-resources.js', () => ({
  configService: {
    listRepositories: mockListRepositories,
  },
}));

const mockAccountServerFetch = vi.fn();
vi.mock('../account-client.js', () => ({
  accountServerFetch: (...args: unknown[]) => mockAccountServerFetch(...args),
}));

describe('refreshRepoLicensesBatch', () => {
  const machine: MachineConfig = {
    ip: '127.0.0.1',
    user: 'root',
    port: 22,
    datastore: '/mnt/rediacc',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockListRepositories.mockResolvedValue([
      {
        name: 'mail',
        config: {
          repositoryGuid: '550e8400-e29b-41d4-a716-446655440000',
        },
      },
    ]);
    mockExec
      .mockResolvedValueOnce('3a62c0cf8d150bed7ca40e9d6de237eb26b96dee26d7a20eb866e09bd1aca09b\n')
      .mockResolvedValueOnce(
        JSON.stringify([
          {
            repositoryGuid: '550e8400-e29b-41d4-a716-446655440000',
            requestedSizeGb: 4,
            luksUuid: '550e8400-e29b-41d4-a716-446655440001',
          },
          {
            repositoryGuid: '550e8400-e29b-41d4-a716-446655440002',
            requestedSizeGb: 2,
            storageFingerprint: 'file:1:2:3',
            currentRefreshRecommendedAt: '2099-01-01T00:00:00.000Z',
            currentHardExpiresAt: '2099-02-01T00:00:00.000Z',
          },
        ])
      )
      .mockResolvedValueOnce(JSON.stringify([])); // license-status (no invalid signatures)
    mockExecStreaming.mockResolvedValue(0);
  });

  it('writes only issued/refreshed licenses and reports mixed batch result', async () => {
    mockAccountServerFetch.mockResolvedValueOnce({
      results: [
        {
          repositoryGuid: '550e8400-e29b-41d4-a716-446655440000',
          status: 'issued',
          license: { payload: 'a', signature: 'b', publicKeyId: 'c' },
        },
        {
          repositoryGuid: '550e8400-e29b-41d4-a716-446655440003',
          status: 'failed',
          error: 'size limit exceeded',
        },
      ],
    });

    const result = await refreshRepoLicensesBatch(machine, 'dummy-key', '/usr/bin/renet');

    expect(result).toEqual({
      scanned: 2,
      issued: 1,
      refreshed: 0,
      unchanged: 0,
      failed: 2,
      valid: 1,
      invalidSignatureDetected: 0,
      failures: [
        {
          repositoryGuid: '550e8400-e29b-41d4-a716-446655440002',
          error: 'Repository exists on target machine but is not tracked in local config',
        },
        {
          repositoryGuid: '550e8400-e29b-41d4-a716-446655440003',
          error: 'size limit exceeded',
        },
      ],
    });
    expect(mockAccountServerFetch).toHaveBeenCalledTimes(1);
    expect(mockExecStreaming).toHaveBeenCalledTimes(1);
  });

  it('fails unknown repos locally without issuing any batch request when nothing is tracked', async () => {
    mockListRepositories.mockResolvedValueOnce([]);

    const result = await refreshRepoLicensesBatch(machine, 'dummy-key', '/usr/bin/renet');

    expect(result).toEqual({
      scanned: 2,
      issued: 0,
      refreshed: 0,
      unchanged: 0,
      failed: 2,
      valid: 0,
      invalidSignatureDetected: 0,
      failures: [
        {
          repositoryGuid: '550e8400-e29b-41d4-a716-446655440000',
          error: 'Repository exists on target machine but is not tracked in local config',
        },
        {
          repositoryGuid: '550e8400-e29b-41d4-a716-446655440002',
          error: 'Repository exists on target machine but is not tracked in local config',
        },
      ],
    });
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
    expect(mockExecStreaming).not.toHaveBeenCalled();
  });

  it('does not write unchanged entries returned by the server', async () => {
    mockAccountServerFetch.mockResolvedValueOnce({
      results: [
        {
          repositoryGuid: '550e8400-e29b-41d4-a716-446655440000',
          status: 'unchanged',
        },
      ],
    });

    const result = await refreshRepoLicensesBatch(machine, 'dummy-key', '/usr/bin/renet');

    expect(result.unchanged).toBe(1);
    expect(mockExecStreaming).not.toHaveBeenCalled();
  });

  it('surfaces parsed batch request failures from the account server', async () => {
    const error = new Error('Monthly repo license issuance limit reached');
    (error as Record<string, unknown>).status = 403;
    mockAccountServerFetch.mockRejectedValueOnce(error);

    await expect(refreshRepoLicensesBatch(machine, 'dummy-key', '/usr/bin/renet')).rejects.toThrow(
      'Monthly repo license issuance limit reached'
    );
  });

  it('detects invalid_signature repos and omits their dates to force re-issuance', async () => {
    // Override the license-status mock (3rd exec call) to report invalid_signature
    mockExec.mockReset();
    mockExec
      .mockResolvedValueOnce('3a62c0cf8d150bed7ca40e9d6de237eb26b96dee26d7a20eb866e09bd1aca09b\n')
      .mockResolvedValueOnce(
        JSON.stringify([
          {
            repositoryGuid: '550e8400-e29b-41d4-a716-446655440000',
            requestedSizeGb: 4,
            luksUuid: '550e8400-e29b-41d4-a716-446655440001',
            currentRefreshRecommendedAt: '2099-01-01T00:00:00.000Z',
            currentHardExpiresAt: '2099-02-01T00:00:00.000Z',
          },
        ])
      )
      .mockResolvedValueOnce(
        JSON.stringify([
          {
            repositoryGuid: '550e8400-e29b-41d4-a716-446655440000',
            status: 'invalid_signature',
            message: 'invalid license signature',
            runtimeValid: false,
            installed: true,
          },
        ])
      );

    mockAccountServerFetch.mockResolvedValueOnce({
      results: [
        {
          repositoryGuid: '550e8400-e29b-41d4-a716-446655440000',
          status: 'refreshed',
          license: { payload: 'new-a', signature: 'new-b', publicKeyId: 'default' },
        },
      ],
    });

    const result = await refreshRepoLicensesBatch(machine, 'dummy-key', '/usr/bin/renet');

    expect(result.invalidSignatureDetected).toBe(1);
    expect(result.refreshed).toBe(1);
    expect(result.unchanged).toBe(0);

    // Verify the batch request omitted dates for the invalid-signature repo
    const batchBody = mockAccountServerFetch.mock.calls[0][1].body;
    const repo = batchBody.repos[0];
    expect(repo.currentRefreshRecommendedAt).toBeUndefined();
    expect(repo.currentHardExpiresAt).toBeUndefined();
  });

  it('gracefully degrades when license-status command fails', async () => {
    // Override: license-status throws (e.g., old renet binary)
    mockExec.mockReset();
    mockExec
      .mockResolvedValueOnce('3a62c0cf8d150bed7ca40e9d6de237eb26b96dee26d7a20eb866e09bd1aca09b\n')
      .mockResolvedValueOnce(
        JSON.stringify([
          {
            repositoryGuid: '550e8400-e29b-41d4-a716-446655440000',
            requestedSizeGb: 4,
            luksUuid: '550e8400-e29b-41d4-a716-446655440001',
          },
        ])
      )
      .mockRejectedValueOnce(new Error('unknown command "repository license-status"'));

    mockAccountServerFetch.mockResolvedValueOnce({
      results: [
        {
          repositoryGuid: '550e8400-e29b-41d4-a716-446655440000',
          status: 'issued',
          license: { payload: 'a', signature: 'b', publicKeyId: 'c' },
        },
      ],
    });

    const result = await refreshRepoLicensesBatch(machine, 'dummy-key', '/usr/bin/renet');

    // Should still work — dates are sent normally when license-status fails
    expect(result.invalidSignatureDetected).toBe(0);
    expect(result.issued).toBe(1);
  });
});
