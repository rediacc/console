import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  mockOutputInfo,
  mockOutputWarn,
  mockSaveStoredSubscriptionToken,
  mockGetSubscriptionServerUrl,
  mockGetSubscriptionScopeMismatch,
  mockExecFile,
  mockAccountServerFetch,
} = vi.hoisted(() => ({
  mockOutputInfo: vi.fn(),
  mockOutputWarn: vi.fn(),
  mockSaveStoredSubscriptionToken: vi.fn(),
  mockGetSubscriptionServerUrl: vi.fn(() => 'http://localhost:4800'),
  mockGetSubscriptionScopeMismatch: vi.fn((token, configTeamName) => {
    if (configTeamName && token.teamName && configTeamName !== token.teamName) {
      return `Stored subscription token is bound to team "${token.teamName}", but the current config team is "${configTeamName}". Run "rdc subscription login" again after selecting the correct team.`;
    }
    return null;
  }),
  mockExecFile: vi.fn(),
  mockAccountServerFetch: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string) => key,
}));

vi.mock('../output.js', () => ({
  outputService: {
    info: mockOutputInfo,
    warn: mockOutputWarn,
  },
}));

vi.mock('../subscription-auth.js', () => ({
  getSubscriptionServerUrl: mockGetSubscriptionServerUrl,
  saveStoredSubscriptionToken: mockSaveStoredSubscriptionToken,
  getSubscriptionScopeMismatch: mockGetSubscriptionScopeMismatch,
}));

vi.mock('node:child_process', () => ({
  execFile: mockExecFile,
}));

vi.mock('../account-client.js', () => ({
  accountServerFetch: mockAccountServerFetch,
}));

const { authorizeSubscriptionViaDeviceCode } = await import('../subscription-device-auth.js');

describe('authorizeSubscriptionViaDeviceCode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it('prints the verification URL and errors immediately in non-interactive mode', async () => {
    mockAccountServerFetch.mockResolvedValueOnce({
      deviceCode: 'device-1',
      verificationUrl: 'http://localhost:4800/account/authorize?code=ABCD-EFGH-IJ',
      interval: 5,
      expiresIn: 300,
    });

    await expect(
      authorizeSubscriptionViaDeviceCode(undefined, { interactive: false, announceIntro: true })
    ).rejects.toThrow('errors.subscription.notLoggedIn');

    expect(mockOutputWarn).toHaveBeenCalledWith('commands.subscription.login.waitingApproval');
    expect(mockOutputInfo).toHaveBeenCalledWith(
      '  http://localhost:4800/account/authorize?code=ABCD-EFGH-IJ'
    );
    expect(mockSaveStoredSubscriptionToken).not.toHaveBeenCalled();
  });

  it('polls, validates, and stores the token in interactive mode', async () => {
    vi.useFakeTimers();
    mockAccountServerFetch
      // 1. POST /device-codes
      .mockResolvedValueOnce({
        deviceCode: 'device-1',
        verificationUrl: 'http://localhost:4800/account/authorize?code=ABCD-EFGH-IJ',
        interval: 1,
        expiresIn: 60,
      })
      // 2. GET /device-codes/{code} (poll)
      .mockResolvedValueOnce({
        status: 'complete',
        token: 'rdt_new',
      })
      // 3. GET /licenses/status
      .mockResolvedValueOnce({
        subscriptionId: 'sub_1',
        orgId: 'org_1',
        orgName: 'Acme',
        planCode: 'COMMUNITY',
        activeMachineCount: 1,
        maxMachines: 2,
        teamId: 'team_1',
        teamName: 'Platform',
      });

    const promise = authorizeSubscriptionViaDeviceCode(undefined, {
      interactive: true,
      teamName: 'Platform',
    });
    await vi.advanceTimersByTimeAsync(1000);
    const result = await promise;

    expect(result).toEqual({
      storedToken: {
        token: 'rdt_new',
        serverUrl: 'http://localhost:4800',
        subscriptionId: 'sub_1',
        orgId: 'org_1',
        orgName: 'Acme',
        teamId: 'team_1',
        teamName: 'Platform',
      },
      status: {
        subscriptionId: 'sub_1',
        orgId: 'org_1',
        orgName: 'Acme',
        planCode: 'COMMUNITY',
        activeMachineCount: 1,
        maxMachines: 2,
        teamId: 'team_1',
        teamName: 'Platform',
      },
    });
    expect(mockSaveStoredSubscriptionToken).toHaveBeenCalledWith({
      token: 'rdt_new',
      serverUrl: 'http://localhost:4800',
      subscriptionId: 'sub_1',
      orgId: 'org_1',
      orgName: 'Acme',
      teamId: 'team_1',
      teamName: 'Platform',
    });
  });

  it('fails hard when the approved token team differs from the local config team', async () => {
    vi.useFakeTimers();
    mockAccountServerFetch
      .mockResolvedValueOnce({
        deviceCode: 'device-1',
        verificationUrl: 'http://localhost:4800/account/authorize?code=ABCD-EFGH-IJ',
        interval: 1,
        expiresIn: 60,
      })
      .mockResolvedValueOnce({
        status: 'complete',
        token: 'rdt_new',
      })
      .mockResolvedValueOnce({
        subscriptionId: 'sub_1',
        orgId: 'org_1',
        orgName: 'Acme',
        planCode: 'COMMUNITY',
        activeMachineCount: 1,
        maxMachines: 2,
        teamId: 'team_1',
        teamName: 'Platform',
      });

    const promise = authorizeSubscriptionViaDeviceCode(undefined, {
      interactive: true,
      teamName: 'Infra',
    });
    promise.catch(() => {});
    await vi.advanceTimersByTimeAsync(1000);
    await expect(promise).rejects.toThrow('Platform');
    expect(mockSaveStoredSubscriptionToken).not.toHaveBeenCalled();
  });
});
