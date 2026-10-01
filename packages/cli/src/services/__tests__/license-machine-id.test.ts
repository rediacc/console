import { WK_ACCOUNT_DEV_PORT } from '@rediacc/shared/config/well-known.generated';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SFTPClient } from '../../remote/sftp/index.js';
import type { MachineConfig } from '../../types/index.js';
import { fetchSubscriptionLicenseReport, readMachineActivationStatus } from '../account/license.js';
import { readRemoteMachineId } from '../account/license-machine.js';

const mockExec = vi.fn();
const mockExecStreaming = vi.fn();
const mockConnect = vi.fn();
const mockClose = vi.fn();

vi.mock('../../remote/sftp/index.js', () => ({
  SFTPClient: class MockSFTPClient {
    connect = mockConnect;
    exec = mockExec;
    execStreaming = mockExecStreaming;
    close = mockClose;
  },
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

describe('license machine-id resolution', () => {
  const machine: MachineConfig = {
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

describe('readRemoteMachineId reads the id as root only', () => {
  const ROOT_ID = 'c99b905ad8189fccdef899a8e13e74f6b41622617c4fc031478bb33ce47dc3d5';
  const NON_ROOT_ID = 'a66b5f9009fa96191eaae21d68e57a248dc2a9b48bdd3505f9684ad8ae7ef69c';

  /** A remote that answers like VM .11: root gets one id, the SSH user another. */
  function fakeRemote(sudo: 'ok' | 'refused') {
    const commands: string[] = [];
    const exec = vi.fn((command: string) => {
      commands.push(command);
      if (command.startsWith('sudo ')) {
        return sudo === 'ok'
          ? Promise.resolve(`${ROOT_ID}\n`)
          : Promise.reject(new Error('Command exited with code 1: sudo: a password is required'));
      }
      return Promise.resolve(`${NON_ROOT_ID}\n`);
    });
    return { sftp: { exec } as unknown as SFTPClient, commands };
  }

  it('runs renet under non-interactive sudo, once, and returns the root id', async () => {
    const { sftp, commands } = fakeRemote('ok');
    await expect(readRemoteMachineId(sftp, '/usr/bin/renet')).resolves.toBe(ROOT_ID);
    expect(commands).toEqual(['sudo -n /usr/bin/renet machine-id']);
  });

  it('defaults to renet on PATH, still under sudo', async () => {
    const { sftp, commands } = fakeRemote('ok');
    await expect(readRemoteMachineId(sftp)).resolves.toBe(ROOT_ID);
    expect(commands).toEqual(['sudo -n renet machine-id']);
  });

  it('fails loudly with the cause when sudo is refused, never falling back to the non-root id', async () => {
    const { sftp, commands } = fakeRemote('refused');
    await expect(readRemoteMachineId(sftp)).rejects.toThrow(/sudo: a password is required/);
    expect(commands).toHaveLength(1);
    expect(commands.some((c) => !c.startsWith('sudo -n '))).toBe(false);
  });

  it('rejects output that is not a machine id', async () => {
    const sftp = { exec: vi.fn(() => Promise.resolve('not-an-id\n')) } as unknown as SFTPClient;
    await expect(readRemoteMachineId(sftp)).rejects.toThrow(/did not print a machine ID/);
  });
});
