import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MachineConfig } from '../../types/index.js';
import {
  fetchSubscriptionLicenseReport,
  readMachineActivationStatus,
  refreshMachineActivation,
} from '../license.js';

const mockExec = vi.fn();
const mockExecStreaming = vi.fn();
const mockConnect = vi.fn();
const mockClose = vi.fn();

vi.mock('@rediacc/shared-desktop/sftp', () => ({
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

describe('refreshMachineActivation machine-id resolution', () => {
  const machine: MachineConfig = {
    machineName: 'hostinger',
    ip: '127.0.0.1',
    user: 'root',
    port: 22,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
  });

  it('fails when remote machine-id is not renet fingerprint format', async () => {
    mockExec.mockResolvedValueOnce('e3911b6fa57d4f48ab14418acd119706\n');

    await expect(refreshMachineActivation(machine, 'dummy-key')).rejects.toThrow(
      'Failed to resolve remote renet machine ID'
    );
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('refreshes activation when remote machine-id is a 64-char fingerprint', async () => {
    mockExec.mockResolvedValueOnce(
      '3a62c0cf8d150bed7ca40e9d6de237eb26b96dee26d7a20eb866e09bd1aca09b\n'
    );
    vi.mocked(global.fetch).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ activation: { machineId: 'x' } }),
    } as Response);

    const result = await refreshMachineActivation(machine, 'dummy-key', '/usr/bin/renet');
    expect(result).toBe(true);
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(mockExecStreaming).not.toHaveBeenCalled();
  });

  it('fetches the subscription report when token state is ready', async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          subscriptionId: 'sub_1',
          planCode: 'COMMUNITY',
          status: 'active',
        }),
    } as Response);

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
    vi.mocked(global.fetch).mockResolvedValueOnce({
      ok: false,
    } as Response);

    const result = await readMachineActivationStatus(machine, 'dummy-key', '/usr/bin/renet');
    expect(result).toBeNull();
  });

  it('returns active machine activation details when report contains the machine', async () => {
    const machineId = '3a62c0cf8d150bed7ca40e9d6de237eb26b96dee26d7a20eb866e09bd1aca09b';
    mockExec.mockResolvedValueOnce(`${machineId}\n`);
    vi.mocked(global.fetch).mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
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
        }),
    } as Response);

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
