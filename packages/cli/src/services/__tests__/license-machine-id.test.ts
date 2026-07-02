import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MachineConfig } from '../../types/index.js';
import { fetchSubscriptionLicenseReport, readMachineActivationStatus } from '../license.js';

const mockExec = vi.fn();
const mockExecStreaming = vi.fn();
const mockConnect = vi.fn();
const mockClose = vi.fn();

vi.mock('../../shared-desktop/sftp/index.js', () => ({
  SFTPClient: class MockSFTPClient {
    connect = mockConnect;
    exec = mockExec;
    execStreaming = mockExecStreaming;
    close = mockClose;
  },
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

describe('license machine-id resolution', () => {
  const machine: MachineConfig = {
    machineName: 'hostinger',
    ip: '127.0.0.1',
    user: 'root',
    port: 22,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches the subscription report when token state is ready', async () => {
    mockAccountServerFetch.mockResolvedValueOnce({
      subscriptionId: 'sub_1',
      planCode: 'COMMUNITY',
      status: 'active',
    });

    await expect(fetchSubscriptionLicenseReport()).resolves.toEqual({
      subscriptionId: 'sub_1',
      planCode: 'COMMUNITY',
      status: 'active',
    });
  });

  it('returns null machine activation status when the report cannot be fetched', async () => {
    mockExec.mockResolvedValueOnce(
      '3a62c0cf8d150bed7ca40e9d6de237eb26b96dee26d7a20eb866e09bd1aca09b\n'
    );
    mockAccountServerFetch.mockRejectedValueOnce(new Error('HTTP 500'));

    const result = await readMachineActivationStatus(machine, 'dummy-key', '/usr/bin/renet');
    expect(result).toBeNull();
  });

  it('returns active machine activation details when report contains the machine', async () => {
    const machineId = '3a62c0cf8d150bed7ca40e9d6de237eb26b96dee26d7a20eb866e09bd1aca09b';
    mockExec.mockResolvedValueOnce(`${machineId}\n`);
    mockAccountServerFetch.mockResolvedValueOnce({
      subscriptionId: 'sub_1',
      planCode: 'COMMUNITY',
      status: 'active',
      machineSlots: {
        active: 1,
        max: 2,
        machines: [{ machineId, lastSeenAt: '2026-03-12T00:00:00Z' }],
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

    await expect(
      readMachineActivationStatus(machine, 'dummy-key', '/usr/bin/renet')
    ).resolves.toEqual({
      machineId,
      active: true,
      lastSeenAt: '2026-03-12T00:00:00Z',
      activeCount: 1,
      maxCount: 2,
    });
  });
});
