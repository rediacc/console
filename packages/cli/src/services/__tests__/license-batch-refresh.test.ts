import {
  WK_ACCOUNT_DEV_PORT,
  WK_DATASTORE_PATH,
} from '@rediacc/shared/config/well-known.generated';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MachineConfig } from '../../types/index.js';
import { refreshRepoLicensesBatch } from '../account/license.js';
import type { SubscriptionTokenState } from '../account/subscription-auth.js';

// A well-formed signing-key fingerprint (16-char lowercase hex). writeRepoLicense now names the license file after this and rejects anything else.
const VALID_KEY_ID = 'fc6a12b178711e65';
const REPO_GUID = '550e8400-e29b-41d4-a716-446655440000';
const MACHINE_NAME = 'test-machine';
const MACHINE_ID = '3a62c0cf8d150bed7ca40e9d6de237eb26b96dee26d7a20eb866e09bd1aca09b';

const { mockGetSubscriptionTokenState } = vi.hoisted(() => ({
  mockGetSubscriptionTokenState: vi.fn(
    (): SubscriptionTokenState => ({
      kind: 'ready',
      serverUrl: `http://localhost:${WK_ACCOUNT_DEV_PORT}`,
      token: { token: 'rdt_test', serverUrl: `http://localhost:${WK_ACCOUNT_DEV_PORT}` },
    })
  ),
}));

const { mockExec, mockExecStreaming, mockConnect, mockClose, mockListRepositories, mockExecute } =
  vi.hoisted(() => ({
    mockExec: vi.fn(),
    mockExecStreaming: vi.fn(),
    mockConnect: vi.fn(),
    mockClose: vi.fn(),
    mockListRepositories: vi.fn(),
    mockExecute: vi.fn(),
  }));

vi.mock('../executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecute }),
}));

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
    datastore: WK_DATASTORE_PATH,
  };

  /** What each renet command-kind job answers; an Error status models a failing job. */
  const jobs: { scan: unknown[]; status: unknown[] | Error } = { scan: [], status: [] };

  /** Every job the CLI sent, by command kind. */
  function sentJobs(name: string): { args: Record<string, unknown>; payload?: string }[] {
    return mockExecute.mock.calls
      .map(
        (c) =>
          c[0] as {
            commandKind: { name: string; args: Record<string, unknown>; payload?: string };
          }
      )
      .filter((o) => o.commandKind.name === name)
      .map((o) => o.commandKind);
  }

  /** The parsed license-write payloads. */
  function writes(): {
    repositoryGuid: string;
    datastoreId?: string;
    license: { publicKeyId: string };
  }[] {
    return sentJobs('license-write').map((j) => JSON.parse(j.payload ?? '{}'));
  }

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      serverUrl: `http://localhost:${WK_ACCOUNT_DEV_PORT}`,
      token: { token: 'rdt_test', serverUrl: `http://localhost:${WK_ACCOUNT_DEV_PORT}` },
    });
    mockListRepositories.mockResolvedValue([
      {
        name: 'mail',
        config: {
          repositoryGuid: '550e8400-e29b-41d4-a716-446655440000',
        },
      },
    ]);
    mockExec.mockResolvedValue(`${MACHINE_ID}\n`);
    jobs.scan = [
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
    ];
    jobs.status = []; // license-status (no invalid signatures)
    mockExecute.mockImplementation((opts: { commandKind: { name: string } }) => {
      const { name } = opts.commandKind;
      if (name === 'license-write') {
        return Promise.resolve({ success: true, exitCode: 0, stdout: '' });
      }
      if (name === 'license-scan') {
        return Promise.resolve({ success: true, exitCode: 0, stdout: JSON.stringify(jobs.scan) });
      }
      if (jobs.status instanceof Error) return Promise.reject(jobs.status);
      return Promise.resolve({ success: true, exitCode: 0, stdout: JSON.stringify(jobs.status) });
    });
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

    const result = await refreshRepoLicensesBatch(
      MACHINE_NAME,
      machine,
      'dummy-key',
      '/usr/bin/renet'
    );

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
    expect(sentJobs('license-write')).toHaveLength(1);
  });

  it('fails unknown repos locally without issuing any batch request when nothing is tracked', async () => {
    mockListRepositories.mockResolvedValueOnce([]);

    const result = await refreshRepoLicensesBatch(
      MACHINE_NAME,
      machine,
      'dummy-key',
      '/usr/bin/renet'
    );

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
    expect(sentJobs('license-write')).toHaveLength(0);
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

    const result = await refreshRepoLicensesBatch(
      MACHINE_NAME,
      machine,
      'dummy-key',
      '/usr/bin/renet'
    );

    expect(result.unchanged).toBe(1);
    expect(sentJobs('license-write')).toHaveLength(0);
  });

  it('surfaces parsed batch request failures from the account server', async () => {
    const error = Object.assign(new Error('Monthly repo license issuance limit reached'), {
      status: 403,
    });
    mockAccountServerFetch.mockRejectedValueOnce(error);

    await expect(
      refreshRepoLicensesBatch(MACHINE_NAME, machine, 'dummy-key', '/usr/bin/renet')
    ).rejects.toThrow('Monthly repo license issuance limit reached');
  });

  /** Seed the scan and status jobs with one tracked repo carrying dates + a status. */
  function seedSingleRepoWithStatus(status: string): void {
    jobs.scan = [
      {
        repositoryGuid: REPO_GUID,
        requestedSizeGb: 4,
        luksUuid: '550e8400-e29b-41d4-a716-446655440001',
        currentRefreshRecommendedAt: '2099-01-01T00:00:00.000Z',
        currentHardExpiresAt: '2099-02-01T00:00:00.000Z',
      },
    ];
    jobs.status = [
      {
        repositoryGuid: REPO_GUID,
        status,
        message: `status ${status}`,
        runtimeValid: false,
        installed: true,
      },
    ];
  }

  it('does NOT force re-issuance for invalid_signature (dates preserved, no reissue loop)', async () => {
    // Per the per-signer layout, a foreign file is never selected, so an invalid_signature means the machine's OWN key cannot validate its own file. That must fail fast at operate time, not loop reissuing here.
    seedSingleRepoWithStatus('invalid_signature');

    mockAccountServerFetch.mockResolvedValueOnce({
      results: [{ repositoryGuid: REPO_GUID, status: 'unchanged' }],
    });

    const result = await refreshRepoLicensesBatch(
      MACHINE_NAME,
      machine,
      'dummy-key',
      '/usr/bin/renet'
    );

    expect(result.invalidSignatureDetected).toBe(0);

    // Dates are PRESERVED, the server is free to return "unchanged".
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

    const result = await refreshRepoLicensesBatch(
      MACHINE_NAME,
      machine,
      'dummy-key',
      '/usr/bin/renet'
    );

    expect(result.invalidSignatureDetected).toBe(1);
    expect(result.refreshed).toBe(1);
    expect(result.unchanged).toBe(0);

    // Dates omitted → server is forced to reissue.
    const repo = mockAccountServerFetch.mock.calls[0][1].body.repos[0];
    expect(repo.currentRefreshRecommendedAt).toBeUndefined();
    expect(repo.currentHardExpiresAt).toBeUndefined();
  });

  it('forces re-issuance for identity_mismatch (dates omitted), so an accepted new image is licensed at once', async () => {
    // After `backup snapshot --accept-identity-change` the image's UUID differs from the licence's. On an unexpired licence the account answers `unchanged` to a plain refresh, leaving the repository unmountable until the refresh window; only a forced GUID is reissued.
    seedSingleRepoWithStatus('identity_mismatch');

    mockAccountServerFetch.mockResolvedValueOnce({
      results: [
        {
          repositoryGuid: REPO_GUID,
          status: 'refreshed',
          license: { payload: 'new-a', signature: 'new-b', publicKeyId: VALID_KEY_ID },
        },
      ],
    });

    const result = await refreshRepoLicensesBatch(
      MACHINE_NAME,
      machine,
      'dummy-key',
      '/usr/bin/renet'
    );

    expect(result.invalidSignatureDetected).toBe(1);
    expect(result.refreshed).toBe(1);
    const repo = mockAccountServerFetch.mock.calls[0][1].body.repos[0];
    expect(repo.currentRefreshRecommendedAt).toBeUndefined();
    expect(repo.currentHardExpiresAt).toBeUndefined();
  });

  it('gracefully degrades when license-status command fails', async () => {
    // Override: license-status throws (e.g., old renet binary)
    jobs.scan = [
      {
        repositoryGuid: '550e8400-e29b-41d4-a716-446655440000',
        requestedSizeGb: 4,
        luksUuid: '550e8400-e29b-41d4-a716-446655440001',
      },
    ];
    jobs.status = new Error('unknown command "repository license-status"');

    mockAccountServerFetch.mockResolvedValueOnce({
      results: [
        {
          repositoryGuid: '550e8400-e29b-41d4-a716-446655440000',
          status: 'issued',
          license: { payload: 'a', signature: 'b', publicKeyId: VALID_KEY_ID },
        },
      ],
    });

    const result = await refreshRepoLicensesBatch(
      MACHINE_NAME,
      machine,
      'dummy-key',
      '/usr/bin/renet'
    );

    // Should still work, dates are sent normally when license-status fails
    expect(result.invalidSignatureDetected).toBe(0);
    expect(result.issued).toBe(1);
  });

  it('returns recoveryFailureMode=token_not_ready when subscription token is not ready', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({ kind: 'missing' });

    const result = await refreshRepoLicensesBatch(
      MACHINE_NAME,
      machine,
      'dummy-key',
      '/usr/bin/renet'
    );

    expect(result.recoveryFailureMode).toBe('token_not_ready');
    expect(result.valid).toBe(0);
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });

  it('returns recoveryFailureMode=no_known_repos when remote scan finds repos not in local config', async () => {
    mockListRepositories.mockResolvedValueOnce([]);

    const result = await refreshRepoLicensesBatch(
      MACHINE_NAME,
      machine,
      'dummy-key',
      '/usr/bin/renet'
    );

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

    const result = await refreshRepoLicensesBatch(
      MACHINE_NAME,
      machine,
      'dummy-key',
      '/usr/bin/renet'
    );

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

    const result = await refreshRepoLicensesBatch(
      MACHINE_NAME,
      machine,
      'dummy-key',
      '/usr/bin/renet'
    );

    expect(result.recoveryFailureMode).toBeNull();
    expect(result.valid).toBeGreaterThan(0);
  });

  describe('per-signer write path', () => {
    // renet places the file (<guid>/<keyId>.json, chmod, legacy GC) when it installs the blob, so the CLI's part is the license-write payload: the guid, the blob (whose publicKeyId names the file) and no datastore identity.
    it('sends the blob under its guid as a license-write payload, unscoped for a default-datastore repo', async () => {
      mockAccountServerFetch.mockResolvedValueOnce({
        results: [
          {
            repositoryGuid: REPO_GUID,
            status: 'issued',
            license: { payload: 'a', signature: 'b', publicKeyId: VALID_KEY_ID },
          },
        ],
      });

      await refreshRepoLicensesBatch(MACHINE_NAME, machine, 'dummy-key', '/usr/bin/renet');

      const sent = sentJobs('license-write');
      expect(sent).toHaveLength(1);
      expect(sent[0].args).toEqual({});
      expect(writes()).toEqual([
        {
          repositoryGuid: REPO_GUID,
          license: { payload: 'a', signature: 'b', publicKeyId: VALID_KEY_ID },
        },
      ]);
      // No shell placement from the CLI any more: only the machine-id probe goes over SFTP.
      expect(mockExec.mock.calls.every((c) => String(c[0]).includes('machine-id'))).toBe(true);
      expect(mockExecStreaming).not.toHaveBeenCalled();
    });

    it('never names another signer’s key id (no-clobber)', async () => {
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

      await refreshRepoLicensesBatch(MACHINE_NAME, machine, 'dummy-key', '/usr/bin/renet');

      expect(writes().map((w) => w.license.publicKeyId)).toEqual([VALID_KEY_ID]);
      const everything = JSON.stringify(mockExecute.mock.calls);
      expect(everything.includes(FOREIGN_KEY_ID)).toBe(false);
    });

    it('fails loudly on a malformed publicKeyId and never sends license-write', async () => {
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
        refreshRepoLicensesBatch(MACHINE_NAME, machine, 'dummy-key', '/usr/bin/renet')
      ).rejects.toThrow(/invalid.*publicKeyId|16-char hex/);

      // Validation happens before any write, so no license-write job was sent.
      expect(sentJobs('license-write')).toHaveLength(0);
    });
  });

  describe('datastore scoping, datastoreId and clusterId', () => {
    const DS_ID = '7f3c9e11-8a4b-4c2d-9e5f-1a2b3c4d5e6f';
    const NAMED_REPO = '550e8400-e29b-41d4-a716-446655440000';

    /** Seed the scan so the tracked repo lives in a NAMED datastore. */
    function seedDatastoreResidentRepo(): void {
      jobs.scan = [
        {
          repositoryGuid: NAMED_REPO,
          requestedSizeGb: 4,
          luksUuid: '550e8400-e29b-41d4-a716-446655440001',
          datastoreId: DS_ID,
          datastorePath: '/mnt/rediacc-ds/fast',
        },
      ];
      mockAccountServerFetch.mockResolvedValueOnce({
        results: [
          {
            repositoryGuid: NAMED_REPO,
            status: 'issued',
            license: { payload: 'a', signature: 'b', publicKeyId: VALID_KEY_ID },
          },
        ],
      });
    }

    it('scans every datastore, not just the machine primary', async () => {
      mockAccountServerFetch.mockResolvedValueOnce({ results: [] });

      await refreshRepoLicensesBatch(MACHINE_NAME, machine, 'dummy-key', '/usr/bin/renet');

      // renet adds --all-datastores to the scan itself; the CLI names the machine's primary datastore and the scan job runs on the right machine.
      const scans = sentJobs('license-scan');
      expect(scans).toHaveLength(1);
      expect(scans[0].args).toEqual({ datastore: WK_DATASTORE_PATH });
      expect(sentJobs('license-status')[0].args).toEqual({ datastore: WK_DATASTORE_PATH });
      expect(mockExecute.mock.calls.every((c) => c[0].machineName === MACHINE_NAME)).toBe(true);
    });

    it('sends the datastore identity so the signed payload is bound to it', async () => {
      seedDatastoreResidentRepo();

      await refreshRepoLicensesBatch(MACHINE_NAME, machine, 'dummy-key', '/usr/bin/renet');

      const body = mockAccountServerFetch.mock.calls[0][1] as {
        body: { repos: { datastoreId?: string }[] };
      };
      expect(body.body.repos[0].datastoreId).toBe(DS_ID);
    });

    it('installs a datastore-resident licence into that datastore’s population', async () => {
      seedDatastoreResidentRepo();

      await refreshRepoLicensesBatch(MACHINE_NAME, machine, 'dummy-key', '/usr/bin/renet');

      // renet reads ONE population per repo and treats the other as absent, so an unscoped write here would read back as `missing`, trigger a reissue, and loop forever burning the monthly issuance quota. renet picks the population from the datastoreId in the payload.
      expect(writes()).toEqual([
        {
          repositoryGuid: NAMED_REPO,
          datastoreId: DS_ID,
          license: { payload: 'a', signature: 'b', publicKeyId: VALID_KEY_ID },
        },
      ]);
    });

    it('keeps the legacy unscoped path for a repo with no datastore identity', async () => {
      mockAccountServerFetch.mockResolvedValueOnce({
        results: [
          {
            repositoryGuid: NAMED_REPO,
            status: 'issued',
            license: { payload: 'a', signature: 'b', publicKeyId: VALID_KEY_ID },
          },
        ],
      });

      await refreshRepoLicensesBatch(MACHINE_NAME, machine, 'dummy-key', '/usr/bin/renet');

      // The plain default datastore carries no descriptor, so renet keeps reading repos/<guid>/ for it. Scoping those would orphan every existing licence on every existing machine: the payload carries no datastoreId.
      const [written] = writes();
      expect(written.repositoryGuid).toBe(NAMED_REPO);
      expect(written).not.toHaveProperty('datastoreId');
    });

    it('sends the cluster the machine belongs to, and omits it when it belongs to none', async () => {
      const clustered: MachineConfig = { ...machine, cluster: { cluster: 'prod', pool: 'k8s' } };
      mockAccountServerFetch.mockResolvedValueOnce({ results: [] });

      await refreshRepoLicensesBatch(MACHINE_NAME, clustered, 'dummy-key', '/usr/bin/renet');

      const body = mockAccountServerFetch.mock.calls[0][1] as {
        body: { clusterId?: string; repos: { clusterId?: string }[] };
      };
      expect(body.body.clusterId).toBe('prod');
      expect(body.body.repos[0].clusterId).toBe('prod');

      mockAccountServerFetch.mockClear();
      jobs.scan = [{ repositoryGuid: NAMED_REPO, requestedSizeGb: 4 }];
      mockAccountServerFetch.mockResolvedValueOnce({ results: [] });

      await refreshRepoLicensesBatch(MACHINE_NAME, machine, 'dummy-key', '/usr/bin/renet');

      const plain = mockAccountServerFetch.mock.calls[0][1] as { body: { clusterId?: string } };
      expect(plain.body.clusterId).toBeUndefined();
    });
  });

  describe('requiredGuid (the repo renet refused)', () => {
    const X = '550e8400-e29b-41d4-a716-446655440000';
    const Y = '550e8400-e29b-41d4-a716-446655440002';
    const license = { payload: 'a', signature: 'b', publicKeyId: VALID_KEY_ID };

    beforeEach(() => {
      mockListRepositories.mockResolvedValue([
        { name: 'x', config: { repositoryGuid: X } },
        { name: 'y', config: { repositoryGuid: Y } },
      ]);
    });

    it('fails when only another repo on the machine was licensed', async () => {
      mockAccountServerFetch.mockResolvedValueOnce({
        results: [
          { repositoryGuid: X, status: 'failed', error: 'size limit exceeded' },
          { repositoryGuid: Y, status: 'issued', license },
        ],
      });
      const result = await refreshRepoLicensesBatch(
        MACHINE_NAME,
        machine,
        'dummy-key',
        '/usr/bin/renet',
        undefined,
        X
      );
      expect(result.valid).toBe(1);
      expect(result.recoveryFailureMode).toBe('server_rejected_all');
      expect(result.serverErrorSample).toBe('size limit exceeded');
    });

    it('succeeds when the refused repo itself came back licensed', async () => {
      mockAccountServerFetch.mockResolvedValueOnce({
        results: [
          { repositoryGuid: X, status: 'unchanged' },
          { repositoryGuid: Y, status: 'failed', error: 'nope' },
        ],
      });
      const result = await refreshRepoLicensesBatch(
        MACHINE_NAME,
        machine,
        'dummy-key',
        '/usr/bin/renet',
        undefined,
        X
      );
      expect(result.recoveryFailureMode).toBeNull();
    });

    it('counts only issued, refreshed and unchanged as recovery, not an unrecognised status', async () => {
      mockAccountServerFetch.mockResolvedValueOnce({
        results: [{ repositoryGuid: X, status: 'pending' }],
      });
      const result = await refreshRepoLicensesBatch(
        MACHINE_NAME,
        machine,
        'dummy-key',
        '/usr/bin/renet',
        undefined,
        X
      );
      expect(result.recoveryFailureMode).toBe('server_rejected_all');
    });

    it('matches the required GUID case-insensitively', async () => {
      mockAccountServerFetch.mockResolvedValueOnce({
        results: [{ repositoryGuid: X.toUpperCase(), status: 'unchanged' }],
      });
      const result = await refreshRepoLicensesBatch(
        MACHINE_NAME,
        machine,
        'dummy-key',
        '/usr/bin/renet',
        undefined,
        X
      );
      expect(result.recoveryFailureMode).toBeNull();
    });

    it('fails when the refused repo is absent from the server results', async () => {
      mockAccountServerFetch.mockResolvedValueOnce({
        results: [{ repositoryGuid: Y, status: 'refreshed', license }],
      });
      const result = await refreshRepoLicensesBatch(
        MACHINE_NAME,
        machine,
        'dummy-key',
        '/usr/bin/renet',
        undefined,
        X
      );
      expect(result.recoveryFailureMode).toBe('server_rejected_all');
      expect(result.serverErrorSample).toContain(X);
    });
  });
});
