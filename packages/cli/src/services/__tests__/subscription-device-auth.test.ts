import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  mockOutputInfo,
  mockOutputWarn,
  mockSaveStoredSubscriptionToken,
  mockGetSubscriptionServerUrl,
  mockGetSubscriptionScopeMismatch,
  mockExecFile,
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

const { authorizeSubscriptionViaDeviceCode } = await import('../subscription-device-auth.js');

describe('authorizeSubscriptionViaDeviceCode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
    global.fetch = vi.fn();
  });

  it('prints the verification URL and errors immediately in non-interactive mode', async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          deviceCode: 'device-1',
          verificationUrl: 'http://localhost:4800/account/authorize?code=ABCD-EFGH-IJ',
          interval: 5,
          expiresIn: 300,
        }),
    } as Response);

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
    vi.mocked(global.fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            deviceCode: 'device-1',
            verificationUrl: 'http://localhost:4800/account/authorize?code=ABCD-EFGH-IJ',
            interval: 1,
            expiresIn: 60,
          }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'complete',
            token: 'rdt_new',
          }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            subscriptionId: 'sub_1',
            orgId: 'org_1',
            orgName: 'Acme',
            planCode: 'COMMUNITY',
            activeMachineCount: 1,
            maxMachines: 2,
            teamId: 'team_1',
            teamName: 'Platform',
          }),
      } as Response);

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
    vi.mocked(global.fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            deviceCode: 'device-1',
            verificationUrl: 'http://localhost:4800/account/authorize?code=ABCD-EFGH-IJ',
            interval: 1,
            expiresIn: 60,
          }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'complete',
            token: 'rdt_new',
          }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            subscriptionId: 'sub_1',
            orgId: 'org_1',
            orgName: 'Acme',
            planCode: 'COMMUNITY',
            activeMachineCount: 1,
            maxMachines: 2,
            teamId: 'team_1',
            teamName: 'Platform',
          }),
      } as Response);

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
