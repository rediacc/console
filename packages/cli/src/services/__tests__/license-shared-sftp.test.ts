import { WK_ACCOUNT_DEV_PORT } from '@rediacc/shared/config/well-known.generated';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SFTPClient } from '../../remote/sftp/index.js';
import type { MachineConfig } from '../../types/index.js';
import { readMachineActivationStatus, refreshRepoLicenseIdentity } from '../account/license.js';

const MACHINE_ID = '3a62c0cf8d150bed7ca40e9d6de237eb26b96dee26d7a20eb866e09bd1aca09b';
const REPO_GUID = '550e8400-e29b-41d4-a716-446655440000';

const { mockExec, mockExecStreaming, mockConnect, mockClose, mockSftpConstructor, mockExecute } =
  vi.hoisted(() => ({
    mockExecute: vi.fn(),
    mockExec: vi.fn(),
    mockExecStreaming: vi.fn(),
    mockConnect: vi.fn(),
    mockClose: vi.fn(),
    mockSftpConstructor: vi.fn(),
  }));

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

vi.mock('../executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecute }),
}));

vi.mock('node:fs/promises', () => ({
  readFile: vi.fn().mockResolvedValue('client-machine-001\n'),
}));

vi.mock('../account/subscription-auth.js', () => ({
  getSubscriptionTokenState: vi.fn(() => ({
    kind: 'ready',
    serverUrl: `http://localhost:${WK_ACCOUNT_DEV_PORT}`,
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

type JobOpts = { scan?: () => string };

function jobCalls(name: string) {
  return mockExecute.mock.calls
    .map((c) => c[0] as { commandKind: { name: string; args: unknown; payload?: string } })
    .filter((o) => o.commandKind.name === name);
}

function jobPayload(): { repositoryGuid: string; datastoreId?: string } {
  return JSON.parse(jobCalls('license-write')[0].commandKind.payload as string);
}

function installExecutor(opts: JobOpts = {}) {
  mockExecute.mockImplementation((o: { commandKind: { name: string } }) => {
    if (o.commandKind.name === 'license-scan') {
      return Promise.resolve({
        success: true,
        exitCode: 0,
        stdout:
          opts.scan?.() ??
          JSON.stringify([
            { repositoryGuid: REPO_GUID, luksUuid: 'luks-uuid-0001', requestedSizeGb: 5 },
          ]),
      });
    }
    return Promise.resolve({ success: true, exitCode: 0, stdout: '' });
  });
}

function createSharedSftp() {
  const exec = vi.fn((command: string) => {
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
    ip: '127.0.0.1',
    user: 'root',
    port: 22,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    installExecutor();
    mockExec.mockImplementation((command: string) => {
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
      'm1',
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
    // The license write inside issueRepoLicense went out as one license-write job on the machine.
    expect(jobCalls('license-write')).toHaveLength(1);
    expect(jobCalls('license-write')[0]).toMatchObject({ machineName: 'm1' });
    // Identity proofs come from renet's own licence scan job, not from a `stat` of ours: storageFingerprint is a signed field whose bytes renet re-derives.
    expect(jobCalls('license-scan')).toHaveLength(1);
    expect(spies.exec).toHaveBeenCalledWith(expect.stringContaining('machine-id'));
  });

  it('refreshRepoLicenseIdentity without sharedSftp opens a single connection and reuses it for issueRepoLicense', async () => {
    mockAccountServerFetch.mockResolvedValueOnce({
      license: { payload: 'a', signature: 'b', publicKeyId: 'fc6a12b178711e65' },
    });

    const result = await refreshRepoLicenseIdentity(
      'm1',
      machine,
      'dummy-key',
      { repositoryGuid: REPO_GUID, kind: 'grand', requestedSizeGb: 5 },
      '/usr/bin/renet'
    );

    expect(result).toBe(true);
    expect(mockSftpConstructor).toHaveBeenCalledTimes(1);
    expect(mockConnect).toHaveBeenCalledTimes(1);
    expect(mockClose).toHaveBeenCalledTimes(1);
    expect(jobCalls('license-write')).toHaveLength(1);
  });

  // The identity refresh re-issues a repo licence WITH proofs, and it reads the datastore identity out of renet's own licence scan, the right source, because the scan reads where the repo actually lives. But the scan can come back empty (an older renet, a datastore it could not read), and dropping to "no identity" there writes the PROVEN reissue to the unscoped path that renet
  // does not read for a datastore-resident repo. That undoes the pre-issuance scoping one step later, so the caller's resolved identity stands in as a fallback.
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

    it("falls back to the caller's identity when the scan lists the repo with no datastore", async () => {
      const { sftp } = createSharedSftp();

      const result = await refreshRepoLicenseIdentity(
        'm1',
        machine,
        'dummy-key',
        { repositoryGuid: REPO_GUID, kind: 'grand', requestedSizeGb: 5, datastoreId: DS_ID },
        '/usr/bin/renet',
        sftp
      );

      expect(result).toBe(true);
      expect(lastIssuanceBody().datastoreId).toBe(DS_ID);
      expect(jobPayload()).toMatchObject({ repositoryGuid: REPO_GUID, datastoreId: DS_ID });
    });

    it('prefers what the scan saw, because it read the repo where it actually lives', async () => {
      const { sftp } = createSharedSftp();
      installExecutor({
        scan: () =>
          JSON.stringify([
            { repositoryGuid: REPO_GUID, datastoreId: SCANNED_DS_ID, requestedSizeGb: 5 },
          ]),
      });

      await refreshRepoLicenseIdentity(
        'm1',
        machine,
        'dummy-key',
        { repositoryGuid: REPO_GUID, kind: 'grand', requestedSizeGb: 5, datastoreId: DS_ID },
        '/usr/bin/renet',
        sftp
      );

      expect(lastIssuanceBody().datastoreId).toBe(SCANNED_DS_ID);
      expect(jobPayload()).toMatchObject({
        repositoryGuid: REPO_GUID,
        datastoreId: SCANNED_DS_ID,
      });
    });

    it('stays on the legacy unscoped path when neither side names a datastore', async () => {
      const { sftp } = createSharedSftp();

      await refreshRepoLicenseIdentity(
        'm1',
        machine,
        'dummy-key',
        { repositoryGuid: REPO_GUID, kind: 'grand', requestedSizeGb: 5 },
        '/usr/bin/renet',
        sftp
      );

      expect(lastIssuanceBody().datastoreId).toBeUndefined();
      expect(jobPayload().repositoryGuid).toBe(REPO_GUID);
      expect(jobPayload().datastoreId).toBeUndefined();
    });
  });

  // renet's license scan is fail-closed: an image whose LUKS header cannot be read gets NO entry (never a fingerprint minted in place of its UUID). The reissue used to treat "no entry" as "no identity to bind" and issued an unbound licence; it now refuses, naming the repository and the cause.
  describe('a scan that answers without this repository', () => {
    it('refuses the reissue, names the repository and the cause, and asks the account for nothing', async () => {
      const { sftp } = createSharedSftp();
      installExecutor({
        scan: () => JSON.stringify([{ repositoryGuid: 'someone-else', requestedSizeGb: 5 }]),
      });
      const { outputService } = await import('../core/output.js');
      const warn = vi.spyOn(outputService, 'warn').mockImplementation(() => {});

      const result = await refreshRepoLicenseIdentity(
        'm1',
        machine,
        'dummy-key',
        { repositoryGuid: REPO_GUID, kind: 'grand', requestedSizeGb: 5 },
        '/usr/bin/renet',
        sftp
      );

      expect(result).toBe(false);
      expect(mockAccountServerFetch).not.toHaveBeenCalled();
      expect(jobCalls('license-write')).toHaveLength(0);
      const said = warn.mock.calls.map((c) => String(c[0])).join('\n');
      expect(said).toContain(REPO_GUID);
      expect(said).toMatch(/header|identity/i);
      warn.mockRestore();
    });
  });

  describe('a scan that throws', () => {
    it('refuses the reissue like a scan with no entry, and asks the account for nothing', async () => {
      const { sftp } = createSharedSftp();
      installExecutor({ scan: () => 'not json' });
      const { outputService } = await import('../core/output.js');
      const warn = vi.spyOn(outputService, 'warn').mockImplementation(() => {});

      const result = await refreshRepoLicenseIdentity(
        'm1',
        machine,
        'dummy-key',
        { repositoryGuid: REPO_GUID, kind: 'grand', requestedSizeGb: 5 },
        '/usr/bin/renet',
        sftp
      );

      expect(result).toBe(false);
      expect(mockAccountServerFetch).not.toHaveBeenCalled();
      expect(jobCalls('license-write')).toHaveLength(0);
      const said = warn.mock.calls.map((c) => String(c[0])).join('\n');
      expect(said).toContain(REPO_GUID);
      expect(said).toContain('license scan itself failed');
      warn.mockRestore();
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
