import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SFTPClient } from '@rediacc/shared-desktop/sftp';
import type { MachineConfig } from '../../types/index.js';
import { readMachineActivationStatus, refreshRepoLicenseIdentity } from '../license.js';

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

vi.mock('@rediacc/shared-desktop/sftp', () => ({
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

vi.mock('../subscription-auth.js', () => ({
  getSubscriptionTokenState: vi.fn(() => ({
    kind: 'ready',
    serverUrl: 'http://localhost:4800',
    token: { token: 'rdt_test' },
  })),
}));

const mockAccountServerFetch = vi.fn();
vi.mock('../account-client.js', () => ({
  accountServerFetch: (...args: unknown[]) => mockAccountServerFetch(...args),
}));

vi.mock('../telemetry.js', () => ({
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
      license: { payload: 'a', signature: 'b', publicKeyId: 'c' },
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
    expect(spies.exec).toHaveBeenCalledWith(expect.stringContaining('luksUUID'));
    expect(spies.exec).toHaveBeenCalledWith(expect.stringContaining('machine-id'));
  });

  it('refreshRepoLicenseIdentity without sharedSftp opens a single connection and reuses it for issueRepoLicense', async () => {
    mockAccountServerFetch.mockResolvedValueOnce({
      license: { payload: 'a', signature: 'b', publicKeyId: 'c' },
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
