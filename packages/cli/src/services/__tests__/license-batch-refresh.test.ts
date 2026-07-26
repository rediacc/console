import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MachineConfig } from '../../types/index.js';
import { refreshRepoLicensesBatch } from '../account/license.js';

// A well-formed signing-key fingerprint (16-char lowercase hex). writeRepoLicense
// now names the license file after this and rejects anything else.
const VALID_KEY_ID = 'fc6a12b178711e65';
const REPO_GUID = '550e8400-e29b-41d4-a716-446655440000';

const { mockGetSubscriptionTokenState } = vi.hoisted(() => ({
  mockGetSubscriptionTokenState: vi.fn(() => ({
    kind: 'ready',
    serverUrl: 'http://localhost:4800',
    token: { token: 'rdt_test' },
  })),
}));

const { mockExec, mockExecStreaming, mockConnect, mockClose, mockListRepositories } = vi.hoisted(
  () => ({
    mockExec: vi.fn(),
    mockExecStreaming: vi.fn(),
    mockConnect: vi.fn(),
    mockClose: vi.fn(),
    mockListRepositories: vi.fn(),
  })
);

vi.mock('../../remote/sftp/index.js', () => ({
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

vi.mock('../account/subscription-auth.js', () => ({
  getSubscriptionTokenState: mockGetSubscriptionTokenState,
}));

vi.mock('../config/config-resources.js', () => ({
  configService: {
    listRepositories: mockListRepositories,
  },
}));

const mockAccountServerFetch = vi.fn();
vi.mock('../account/account-client.js', () => ({
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
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      serverUrl: 'http://localhost:4800',
      token: { token: 'rdt_test' },
    });
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
          license: { payload: 'a', signature: 'b', publicKeyId: VALID_KEY_ID },
        },
        {
          repositoryGuid: '550e8400-e29b-41d4-a716-446655440003',
          status: 'failed',
          error: 'size limit exceeded',
        },
      ],
    });

    const result = await refreshRepoLicensesBatch(machine, 'dummy-key', '/usr/bin/renet');

    expect(result).toMatchObject({
      scanned: 2,
      issued: 1,
      refreshed: 0,
      unchanged: 0,
      failed: 2,
      valid: 1,
      invalidSignatureDetected: 0,
      recoveryFailureMode: null,
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

    expect(result).toMatchObject({
      scanned: 2,
      issued: 0,
      refreshed: 0,
      unchanged: 0,
      failed: 2,
      valid: 0,
      invalidSignatureDetected: 0,
      recoveryFailureMode: 'no_known_repos',
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

  /** Seed the three read-mocks with one tracked repo carrying dates + a status. */
  function seedSingleRepoWithStatus(status: string): void {
    mockExec.mockReset();
    mockExec
      .mockResolvedValueOnce('3a62c0cf8d150bed7ca40e9d6de237eb26b96dee26d7a20eb866e09bd1aca09b\n')
      .mockResolvedValueOnce(
        JSON.stringify([
          {
            repositoryGuid: REPO_GUID,
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
            repositoryGuid: REPO_GUID,
            status,
            message: `status ${status}`,
            runtimeValid: false,
            installed: true,
          },
        ])
      );
  }

  it('does NOT force re-issuance for invalid_signature (dates preserved, no reissue loop)', async () => {
    // Per the per-signer layout, a foreign file is never selected — so an
    // invalid_signature means the machine's OWN key cannot validate its own
    // file. That must fail fast at operate time, not loop reissuing here.
    seedSingleRepoWithStatus('invalid_signature');

    mockAccountServerFetch.mockResolvedValueOnce({
      results: [{ repositoryGuid: REPO_GUID, status: 'unchanged' }],
    });

    const result = await refreshRepoLicensesBatch(machine, 'dummy-key', '/usr/bin/renet');

    expect(result.invalidSignatureDetected).toBe(0);

    // Dates are PRESERVED — the server is free to return "unchanged".
    const repo = mockAccountServerFetch.mock.calls[0][1].body.repos[0];
    expect(repo.currentRefreshRecommendedAt).toBe('2099-01-01T00:00:00.000Z');
    expect(repo.currentHardExpiresAt).toBe('2099-02-01T00:00:00.000Z');
  });

  it('forces re-issuance for machine_mismatch (dates omitted)', async () => {
    seedSingleRepoWithStatus('machine_mismatch');

    mockAccountServerFetch.mockResolvedValueOnce({
      results: [
        {
          repositoryGuid: REPO_GUID,
          status: 'refreshed',
          license: { payload: 'new-a', signature: 'new-b', publicKeyId: VALID_KEY_ID },
        },
      ],
    });

    const result = await refreshRepoLicensesBatch(machine, 'dummy-key', '/usr/bin/renet');

    expect(result.invalidSignatureDetected).toBe(1);
    expect(result.refreshed).toBe(1);
    expect(result.unchanged).toBe(0);

    // Dates omitted → server is forced to reissue.
    const repo = mockAccountServerFetch.mock.calls[0][1].body.repos[0];
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
          license: { payload: 'a', signature: 'b', publicKeyId: VALID_KEY_ID },
        },
      ],
    });

    const result = await refreshRepoLicensesBatch(machine, 'dummy-key', '/usr/bin/renet');

    // Should still work — dates are sent normally when license-status fails
    expect(result.invalidSignatureDetected).toBe(0);
    expect(result.issued).toBe(1);
  });

  it('returns recoveryFailureMode=token_not_ready when subscription token is not ready', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({ kind: 'missing' });

    const result = await refreshRepoLicensesBatch(machine, 'dummy-key', '/usr/bin/renet');

    expect(result.recoveryFailureMode).toBe('token_not_ready');
    expect(result.valid).toBe(0);
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });

  it('returns recoveryFailureMode=no_known_repos when remote scan finds repos not in local config', async () => {
    mockListRepositories.mockResolvedValueOnce([]);

    const result = await refreshRepoLicensesBatch(machine, 'dummy-key', '/usr/bin/renet');

    expect(result.recoveryFailureMode).toBe('no_known_repos');
    expect(result.valid).toBe(0);
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });

  it('returns recoveryFailureMode=server_rejected_all and serverErrorSample when activate-repo-batch returns failed for all repos', async () => {
    mockAccountServerFetch.mockResolvedValueOnce({
      results: [
        {
          repositoryGuid: '550e8400-e29b-41d4-a716-446655440000',
          status: 'failed',
          error: 'size limit exceeded for this subscription plan',
        },
      ],
    });

    const result = await refreshRepoLicensesBatch(machine, 'dummy-key', '/usr/bin/renet');

    expect(result.recoveryFailureMode).toBe('server_rejected_all');
    expect(result.valid).toBe(0);
    expect(result.serverErrorSample).toContain('size limit exceeded');
  });

  it('returns recoveryFailureMode=null on full success', async () => {
    mockAccountServerFetch.mockResolvedValueOnce({
      results: [
        {
          repositoryGuid: '550e8400-e29b-41d4-a716-446655440000',
          status: 'issued',
          license: { payload: 'a', signature: 'b', publicKeyId: VALID_KEY_ID },
        },
      ],
    });

    const result = await refreshRepoLicensesBatch(machine, 'dummy-key', '/usr/bin/renet');

    expect(result.recoveryFailureMode).toBeNull();
    expect(result.valid).toBeGreaterThan(0);
  });

  describe('per-signer write path', () => {
    const REPO_DIR = `/var/lib/rediacc/license/repos/${REPO_GUID}`;

    it('writes to <guid>/<keyId>.json, chmods it, and GCs the legacy flat file', async () => {
      mockAccountServerFetch.mockResolvedValueOnce({
        results: [
          {
            repositoryGuid: REPO_GUID,
            status: 'issued',
            license: { payload: 'a', signature: 'b', publicKeyId: VALID_KEY_ID },
          },
        ],
      });

      await refreshRepoLicensesBatch(machine, 'dummy-key', '/usr/bin/renet');

      const execCommands = mockExec.mock.calls.map((c) => c[0] as string);
      const teeCommands = mockExecStreaming.mock.calls.map((c) => c[0] as string);
      const perKeyFile = `${REPO_DIR}/${VALID_KEY_ID}.json`;

      expect(execCommands).toContain(`sudo mkdir -p "${REPO_DIR}"`);
      expect(teeCommands).toContain(`sudo tee "${perKeyFile}" > /dev/null`);
      expect(execCommands).toContain(`sudo chmod 640 "${perKeyFile}"`);
      // Legacy flat file is the ONLY rm ever issued.
      expect(execCommands).toContain(
        `sudo rm -f "/var/lib/rediacc/license/repos/${REPO_GUID}.json"`
      );
      const rmCommands = execCommands.filter((c) => c.includes('rm -f'));
      expect(rmCommands).toEqual([`sudo rm -f "/var/lib/rediacc/license/repos/${REPO_GUID}.json"`]);
    });

    it('never names another signer’s file (no-clobber)', async () => {
      const FOREIGN_KEY_ID = 'aaaaaaaaaaaaaaaa';
      mockAccountServerFetch.mockResolvedValueOnce({
        results: [
          {
            repositoryGuid: REPO_GUID,
            status: 'issued',
            license: { payload: 'a', signature: 'b', publicKeyId: VALID_KEY_ID },
          },
        ],
      });

      await refreshRepoLicensesBatch(machine, 'dummy-key', '/usr/bin/renet');

      const allCommands = [
        ...mockExec.mock.calls.map((c) => c[0] as string),
        ...mockExecStreaming.mock.calls.map((c) => c[0] as string),
      ];
      expect(allCommands.some((c) => c.includes(`${FOREIGN_KEY_ID}.json`))).toBe(false);
    });

    it('fails loudly on a malformed publicKeyId and never runs tee', async () => {
      mockAccountServerFetch.mockResolvedValueOnce({
        results: [
          {
            repositoryGuid: REPO_GUID,
            status: 'issued',
            license: { payload: 'a', signature: 'b', publicKeyId: 'default' },
          },
        ],
      });

      await expect(
        refreshRepoLicensesBatch(machine, 'dummy-key', '/usr/bin/renet')
      ).rejects.toThrow(/invalid.*publicKeyId|16-char hex/);

      // Validation happens before any write, so tee/mkdir for the file never ran.
      expect(mockExecStreaming).not.toHaveBeenCalled();
      const execCommands = mockExec.mock.calls.map((c) => c[0] as string);
      expect(execCommands.some((c) => c.includes(REPO_DIR))).toBe(false);
    });
  });
});
