import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SFTPClient } from '../../remote/sftp/index.js';
import type { MachineConfig } from '../../types/index.js';
import { readMachineActivationStatus, refreshRepoLicenseIdentity } from '../account/license.js';

const MACHINE_ID = '3a62c0cf8d150bed7ca40e9d6de237eb26b96dee26d7a20eb866e09bd1aca09b';
const REPO_GUID = '550e8400-e29b-41d4-a716-446655440000';

const { mockExec, mockExecStreaming, mockConnect, mockClose, mockSftpConstructor } = vi.hoisted(
  () => ({
    mockExec: vi.fn(),
    mockExecStreaming: vi.fn(),
    mockConnect: vi.fn(),
    mockClose: vi.fn(),
    mockSftpConstructor: vi.fn(),
  })
);

vi.mock('../../remote/sftp/index.js', () => ({
  SFTPClient: class MockSFTPClient {
    connect = mockConnect;
    exec = mockExec;
    execStreaming = mockExecStreaming;
    close = mockClose;

    constructor(options: unknown) {
      mockSftpConstructor(options);
    }
  },
}));

vi.mock('node:fs/promises', () => ({
  readFile: vi.fn().mockResolvedValue('client-machine-001\n'),
}));

vi.mock('../account/subscription-auth.js', () => ({
  getSubscriptionTokenState: vi.fn(() => ({
    kind: 'ready',
    serverUrl: 'http://localhost:4800',
    token: { token: 'rdt_test' },
  })),
}));

const mockAccountServerFetch = vi.fn();
vi.mock('../account/account-client.js', () => ({
  accountServerFetch: (...args: unknown[]) => mockAccountServerFetch(...args),
}));

vi.mock('../telemetry/telemetry.js', () => ({
  telemetryService: {
    setUserContext: vi.fn(),
    trackError: vi.fn(),
  },
}));

function createSharedSftp() {
  const exec = vi.fn((command: string) => {
    if (command.includes('luksUUID')) return Promise.resolve('luks-uuid-0001\n');
    if (command.includes('machine-id')) return Promise.resolve(`${MACHINE_ID}\n`);
    return Promise.resolve('');
  });
  const sftp = {
    exec,
    execStreaming: vi.fn().mockResolvedValue(0),
    connect: vi.fn(),
    close: vi.fn(),
  };
  return { sftp: sftp as unknown as SFTPClient, spies: sftp };
}

describe('license sharedSftp plumb-through', () => {
  const machine: MachineConfig = {
    machineName: 'hostinger',
    ip: '127.0.0.1',
    user: 'root',
    port: 22,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockExec.mockImplementation((command: string) => {
      if (command.includes('luksUUID')) return Promise.resolve('luks-uuid-0001\n');
      if (command.includes('machine-id')) return Promise.resolve(`${MACHINE_ID}\n`);
      return Promise.resolve('');
    });
    mockExecStreaming.mockResolvedValue(0);
  });

  it('refreshRepoLicenseIdentity uses the provided sharedSftp end-to-end without constructing a new SFTPClient', async () => {
    const { sftp, spies } = createSharedSftp();
    mockAccountServerFetch.mockResolvedValueOnce({
      license: { payload: 'a', signature: 'b', publicKeyId: 'fc6a12b178711e65' },
    });

    const result = await refreshRepoLicenseIdentity(
      machine,
      'dummy-key',
      { repositoryGuid: REPO_GUID, kind: 'grand', requestedSizeGb: 5 },
      '/usr/bin/renet',
      sftp
    );

    expect(result).toBe(true);
    expect(mockSftpConstructor).not.toHaveBeenCalled();
    // The caller owns the shared connection; it must not be opened or closed here.
    expect(spies.connect).not.toHaveBeenCalled();
    expect(spies.close).not.toHaveBeenCalled();
    // The license write inside issueRepoLicense ran on the same shared instance.
    expect(spies.execStreaming).toHaveBeenCalledTimes(1);
    // Identity proofs come from renet's own licence scan, not from a `stat` of
    // ours: storageFingerprint is a signed field whose bytes renet re-derives.
    expect(spies.exec).toHaveBeenCalledWith(expect.stringContaining('license-scan'));
    expect(spies.exec).toHaveBeenCalledWith(expect.stringContaining('machine-id'));
  });

  it('refreshRepoLicenseIdentity without sharedSftp opens a single connection and reuses it for issueRepoLicense', async () => {
    mockAccountServerFetch.mockResolvedValueOnce({
      license: { payload: 'a', signature: 'b', publicKeyId: 'fc6a12b178711e65' },
    });

    const result = await refreshRepoLicenseIdentity(
      machine,
      'dummy-key',
      { repositoryGuid: REPO_GUID, kind: 'grand', requestedSizeGb: 5 },
      '/usr/bin/renet'
    );

    expect(result).toBe(true);
    expect(mockSftpConstructor).toHaveBeenCalledTimes(1);
    expect(mockConnect).toHaveBeenCalledTimes(1);
    expect(mockClose).toHaveBeenCalledTimes(1);
    expect(mockExecStreaming).toHaveBeenCalledTimes(1);
  });

  // The identity refresh re-issues a repo licence WITH proofs, and it reads the
  // datastore identity out of renet's own licence scan — the right source,
  // because the scan reads where the repo actually lives. But the scan can come
  // back empty (an older renet, a datastore it could not read), and dropping to
  // "no identity" there writes the PROVEN reissue to the unscoped path that
  // renet does not read for a datastore-resident repo. That undoes the
  // pre-issuance scoping one step later, so the caller's resolved identity
  // stands in as a fallback.
  describe('datastore identity on the identity refresh', () => {
    const DS_ID = '06a4f728-4c53-4b0e-9f61-2f0a1d3e5c77';
    const SCANNED_DS_ID = '11111111-2222-4333-8444-555555555555';

    function lastIssuanceBody(): { datastoreId?: string } {
      const call = mockAccountServerFetch.mock.calls.at(-1) as [
        string,
        { body: { datastoreId?: string } },
      ];
      return call[1].body;
    }

    beforeEach(() => {
      mockAccountServerFetch.mockResolvedValue({
        license: { payload: 'a', signature: 'b', publicKeyId: 'fc6a12b178711e65' },
      });
    });

    it("falls back to the caller's identity when the scan cannot answer", async () => {
      const { sftp, spies } = createSharedSftp();

      const result = await refreshRepoLicenseIdentity(
        machine,
        'dummy-key',
        { repositoryGuid: REPO_GUID, kind: 'grand', requestedSizeGb: 5, datastoreId: DS_ID },
        '/usr/bin/renet',
        sftp
      );

      expect(result).toBe(true);
      expect(lastIssuanceBody().datastoreId).toBe(DS_ID);
      expect(spies.exec).toHaveBeenCalledWith(
        expect.stringContaining(`/var/lib/rediacc/license/datastores/${DS_ID}/repos/${REPO_GUID}`)
      );
    });

    it('prefers what the scan saw, because it read the repo where it actually lives', async () => {
      const { sftp, spies } = createSharedSftp();
      spies.exec.mockImplementation((command: string) => {
        if (command.includes('machine-id')) return Promise.resolve(`${MACHINE_ID}\n`);
        if (command.includes('license-scan')) {
          return Promise.resolve(
            JSON.stringify([
              { repositoryGuid: REPO_GUID, datastoreId: SCANNED_DS_ID, requestedSizeGb: 5 },
            ])
          );
        }
        return Promise.resolve('');
      });

      await refreshRepoLicenseIdentity(
        machine,
        'dummy-key',
        { repositoryGuid: REPO_GUID, kind: 'grand', requestedSizeGb: 5, datastoreId: DS_ID },
        '/usr/bin/renet',
        sftp
      );

      expect(lastIssuanceBody().datastoreId).toBe(SCANNED_DS_ID);
      expect(spies.exec).toHaveBeenCalledWith(
        expect.stringContaining(
          `/var/lib/rediacc/license/datastores/${SCANNED_DS_ID}/repos/${REPO_GUID}`
        )
      );
    });

    it('stays on the legacy unscoped path when neither side names a datastore', async () => {
      const { sftp, spies } = createSharedSftp();

      await refreshRepoLicenseIdentity(
        machine,
        'dummy-key',
        { repositoryGuid: REPO_GUID, kind: 'grand', requestedSizeGb: 5 },
        '/usr/bin/renet',
        sftp
      );

      expect(lastIssuanceBody().datastoreId).toBeUndefined();
      expect(spies.exec).toHaveBeenCalledWith(
        expect.stringContaining(`/var/lib/rediacc/license/repos/${REPO_GUID}`)
      );
      expect(spies.exec).not.toHaveBeenCalledWith(expect.stringContaining('license/datastores/'));
    });
  });

  it('readMachineActivationStatus prefers the provided sharedSftp and leaves its lifecycle alone', async () => {
    const { sftp, spies } = createSharedSftp();
    mockAccountServerFetch.mockResolvedValueOnce({
      subscriptionId: 'sub_1',
      planCode: 'COMMUNITY',
      status: 'active',
      machineSlots: {
        active: 1,
        max: 2,
        machines: [{ machineId: MACHINE_ID, lastSeenAt: '2026-03-12T00:00:00Z' }],
      },
      repoLicenseIssuances: {
        used: 1,
        limit: 500,
        windowStart: '2026-03-01T00:00:00Z',
        windowEnd: '2026-04-01T00:00:00Z',
      },
      repoLicenses: {
        totalTrackedRepos: 0,
        validCount: 0,
        refreshRecommendedCount: 0,
        hardExpiredCount: 0,
      },
    });

    const result = await readMachineActivationStatus(machine, 'dummy-key', '/usr/bin/renet', sftp);

    expect(result).toMatchObject({ machineId: MACHINE_ID, active: true });
    expect(mockSftpConstructor).not.toHaveBeenCalled();
    expect(spies.connect).not.toHaveBeenCalled();
    expect(spies.close).not.toHaveBeenCalled();
  });
});
