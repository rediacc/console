import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  mockGetSubscriptionTokenState,
  mockFetchSubscriptionLicenseReport,
  mockReadMachineActivationStatus,
  mockReadRuntimeRepoLicenseStatuses,
  mockRefreshMachineActivation,
  mockRefreshRepoLicensesBatch,
  mockAuthorizeSubscriptionViaDeviceCode,
  mockGetLocalConfig,
  mockGetLocalMachine,
  mockGetTeam,
  mockReadSSHKey,
  mockProvisionRenetToRemote,
  mockGetSubscriptionServerUrl,
  mockGetSubscriptionScopeMismatch,
  mockSaveStoredSubscriptionToken,
  mockOutputInfo,
  mockOutputWarn,
  mockOutputSuccess,
  mockWithSpinner,
} = vi.hoisted(() => ({
  mockGetSubscriptionTokenState: vi.fn(),
  mockFetchSubscriptionLicenseReport: vi.fn(),
  mockReadMachineActivationStatus: vi.fn(),
  mockReadRuntimeRepoLicenseStatuses: vi.fn(),
  mockRefreshMachineActivation: vi.fn(),
  mockRefreshRepoLicensesBatch: vi.fn(),
  mockAuthorizeSubscriptionViaDeviceCode: vi.fn(),
  mockGetLocalConfig: vi.fn(),
  mockGetLocalMachine: vi.fn(),
  mockGetTeam: vi.fn(),
  mockReadSSHKey: vi.fn(),
  mockProvisionRenetToRemote: vi.fn(),
  mockGetSubscriptionServerUrl: vi.fn(() => 'http://localhost:4800'),
  mockGetSubscriptionScopeMismatch: vi.fn((token, configTeamName) => {
    if (configTeamName && token.teamName && configTeamName !== token.teamName) {
      return `Stored subscription token is bound to team "${token.teamName}", but the current config team is "${configTeamName}". Run "rdc subscription login" again after selecting the correct team.`;
    }
    return null;
  }),
  mockSaveStoredSubscriptionToken: vi.fn(),
  mockOutputInfo: vi.fn(),
  mockOutputWarn: vi.fn(),
  mockOutputSuccess: vi.fn(),
  mockWithSpinner: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, string | number>) => {
    return vars ? `${key}:${Object.values(vars).join(':')}` : key;
  },
}));

vi.mock('../../services/subscription-auth.js', () => ({
  getSubscriptionTokenState: mockGetSubscriptionTokenState,
  getSubscriptionServerUrl: mockGetSubscriptionServerUrl,
  getSubscriptionScopeMismatch: mockGetSubscriptionScopeMismatch,
  saveStoredSubscriptionToken: mockSaveStoredSubscriptionToken,
}));

vi.mock('../../services/license.js', () => ({
  fetchSubscriptionLicenseReport: mockFetchSubscriptionLicenseReport,
  readMachineActivationStatus: mockReadMachineActivationStatus,
  readRuntimeRepoLicenseStatuses: mockReadRuntimeRepoLicenseStatuses,
  refreshMachineActivation: mockRefreshMachineActivation,
  refreshRepoLicensesBatch: mockRefreshRepoLicensesBatch,
}));

vi.mock('../../services/subscription-device-auth.js', () => ({
  authorizeSubscriptionViaDeviceCode: mockAuthorizeSubscriptionViaDeviceCode,
}));

vi.mock('../../services/config-resources.js', () => ({
  configService: {
    getLocalConfig: mockGetLocalConfig,
    getLocalMachine: mockGetLocalMachine,
    getTeam: mockGetTeam,
  },
}));

vi.mock('../../services/renet-execution.js', () => ({
  readSSHKey: mockReadSSHKey,
  provisionRenetToRemote: mockProvisionRenetToRemote,
}));

vi.mock('../../services/output.js', () => ({
  outputService: {
    info: mockOutputInfo,
    warn: mockOutputWarn,
    success: mockOutputSuccess,
  },
}));

vi.mock('../../utils/spinner.js', () => ({
  withSpinner: mockWithSpinner,
}));

const {
  executeSubscriptionStatus,
  executeActivationStatus,
  executeSubscriptionRefresh,
  executeActivationRefresh,
  executeRepoStatus,
  executeRepoRefresh,
} = await import('../subscription.js');

const { renderRepoBatchRefreshSummary } = await import('../subscription-output.js');

describe('subscription command helpers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockWithSpinner.mockImplementation(async (_label: string, fn: () => Promise<unknown>) => fn());
    mockGetLocalConfig.mockResolvedValue({
      sshPrivateKey: 'PRIVATE_KEY',
      ssh: { privateKeyPath: '/tmp/key' },
    });
    mockGetLocalConfig.mockResolvedValue({
      sshPrivateKey: 'PRIVATE_KEY',
      ssh: { privateKeyPath: '/tmp/key' },
      team: 'Platform',
    });
    mockGetLocalMachine.mockResolvedValue({
      machineName: 'hostinger',
      ip: '127.0.0.1',
      user: 'root',
      port: 22,
    });
    mockGetTeam.mockResolvedValue('Platform');
    mockReadSSHKey.mockResolvedValue('PRIVATE_KEY');
    mockProvisionRenetToRemote.mockResolvedValue({ remotePath: '/usr/bin/renet', uploaded: false });
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      serverUrl: 'http://localhost:4800',
      token: { token: 'rdt_test', teamName: 'Platform', orgName: 'Acme' },
    });
    mockAuthorizeSubscriptionViaDeviceCode.mockResolvedValue({
      storedToken: {
        token: 'rdt_test',
        serverUrl: 'http://localhost:4800',
        subscriptionId: 'sub_1',
        orgName: 'Acme',
        teamName: 'Platform',
      },
      status: {
        subscriptionId: 'sub_1',
        orgName: 'Acme',
        planCode: 'COMMUNITY',
        activeMachineCount: 1,
        maxMachines: 2,
        teamName: 'Platform',
      },
    });
    mockRefreshMachineActivation.mockResolvedValue(true);
    mockReadRuntimeRepoLicenseStatuses.mockResolvedValue([]);
    mockRefreshRepoLicensesBatch.mockResolvedValue({
      scanned: 3,
      issued: 1,
      refreshed: 1,
      unchanged: 1,
      failed: 1,
      valid: 3,
      failures: [{ repositoryGuid: 'repo-bad', error: 'quota reached' }],
    });
  });

  it('status prints only account report information and quota warnings', async () => {
    mockFetchSubscriptionLicenseReport.mockResolvedValue({
      subscriptionId: 'sub_1',
      orgName: 'Acme',
      teamName: 'Platform',
      planCode: 'COMMUNITY',
      status: 'active',
      machineSlots: {
        active: 1,
        max: 2,
        machines: [{ machineId: 'machine-1234567890ab', lastSeenAt: '2026-03-12T00:00:00Z' }],
      },
      repoLicenseIssuances: {
        used: 400,
        limit: 500,
        windowStart: '2026-03-01T00:00:00Z',
        windowEnd: '2026-04-01T00:00:00Z',
      },
      repoLicenses: {
        totalTrackedRepos: 2,
        validCount: 1,
        refreshRecommendedCount: 1,
        hardExpiredCount: 0,
      },
    });

    await executeSubscriptionStatus();

    expect(mockFetchSubscriptionLicenseReport).toHaveBeenCalledTimes(1);
    expect(mockOutputInfo).toHaveBeenCalledWith('commands.subscription.status.remote');
    expect(mockOutputInfo).toHaveBeenCalledWith('Organization: Acme');
    expect(mockOutputInfo).toHaveBeenCalledWith('Team: Platform');
    expect(mockOutputWarn).toHaveBeenCalledWith('commands.subscription.status.issuanceUsageHigh80');
    expect(mockReadMachineActivationStatus).not.toHaveBeenCalled();
  });

  it('status handles missing token state without fetching report', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({ kind: 'missing' });

    await executeSubscriptionStatus();

    expect(mockOutputInfo).toHaveBeenCalledWith('errors.subscription.notLoggedIn');
    expect(mockFetchSubscriptionLicenseReport).not.toHaveBeenCalled();
  });

  it('status warns on server mismatch without fetching report', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'server_mismatch',
      actualServerUrl: 'http://localhost:4830',
      expectedServerUrl: 'http://localhost:4800',
    });

    await executeSubscriptionStatus();

    expect(mockOutputWarn).toHaveBeenCalledWith(
      'commands.subscription.status.serverMismatch:http://localhost:4830:http://localhost:4800'
    );
    expect(mockFetchSubscriptionLicenseReport).not.toHaveBeenCalled();
  });

  it('status fails hard when token team and current config team differ', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({
      kind: 'ready',
      serverUrl: 'http://localhost:4800',
      token: { token: 'rdt_test', teamName: 'Platform' },
    });
    mockGetTeam.mockResolvedValue('Infra');

    await expect(executeSubscriptionStatus()).rejects.toThrow('Platform');
    expect(mockFetchSubscriptionLicenseReport).not.toHaveBeenCalled();
  });

  it('activation-status renders machine activation details only', async () => {
    mockReadMachineActivationStatus.mockResolvedValue({
      machineId: 'machine-activation-id',
      active: true,
      lastSeenAt: '2026-03-12T00:00:00Z',
      activeCount: 1,
      maxCount: 2,
    });

    await executeActivationStatus('hostinger');

    expect(mockReadMachineActivationStatus).toHaveBeenCalledTimes(1);
    expect(mockOutputInfo).toHaveBeenCalledWith(
      'commands.subscription.activation.status.header:hostinger'
    );
    expect(mockOutputInfo).toHaveBeenCalledWith(
      'commands.subscription.activation.status.machineId:machine-activation-id'
    );
    expect(mockOutputSuccess).toHaveBeenCalledWith(
      'commands.subscription.activation.status.active:2026-03-12T00:00:00Z'
    );
    expect(mockFetchSubscriptionLicenseReport).not.toHaveBeenCalled();
  });

  it('repo-status renders runtime repo license statuses from renet', async () => {
    mockReadRuntimeRepoLicenseStatuses.mockResolvedValue([
      {
        repositoryGuid: 'repo-valid',
        status: 'valid',
        runtimeValid: true,
        installed: true,
        hardExpiresAt: '2026-05-10T14:29:53.723Z',
      },
      {
        repositoryGuid: 'repo-missing',
        status: 'missing',
        runtimeValid: false,
        installed: false,
      },
      {
        repositoryGuid: 'repo-machine',
        status: 'machine_mismatch',
        runtimeValid: false,
        installed: true,
      },
    ]);

    await executeRepoStatus('hostinger');

    expect(mockProvisionRenetToRemote).toHaveBeenCalledTimes(1);
    expect(mockReadRuntimeRepoLicenseStatuses).toHaveBeenCalledWith(
      expect.objectContaining({ machineName: 'hostinger' }),
      'PRIVATE_KEY',
      '/usr/bin/renet'
    );
    expect(mockOutputInfo).toHaveBeenCalledWith(
      'commands.subscription.repo.status.header:hostinger'
    );
    expect(mockOutputInfo).toHaveBeenCalledWith(
      'commands.subscription.repo.status.entry:repo-valid:valid:commands.subscription.repo.status.hardExpirySuffix:2026-05-10T14:29:53.723Z'
    );
    expect(mockOutputInfo).toHaveBeenCalledWith(
      'commands.subscription.repo.status.entry:repo-missing:missing:'
    );
    expect(mockOutputInfo).toHaveBeenCalledWith(
      'commands.subscription.repo.status.entry:repo-machine:machine mismatch:'
    );
  });

  it('refresh runs activation refresh before repo batch refresh and prints combined summary', async () => {
    await executeSubscriptionRefresh('hostinger');

    expect(mockRefreshMachineActivation).toHaveBeenCalledTimes(1);
    expect(mockRefreshRepoLicensesBatch).toHaveBeenCalledTimes(1);
    expect(mockRefreshMachineActivation.mock.invocationCallOrder[0]).toBeLessThan(
      mockRefreshRepoLicensesBatch.mock.invocationCallOrder[0]
    );
    expect(mockOutputSuccess).toHaveBeenCalledWith('commands.subscription.refresh.success');
    expect(mockOutputWarn).toHaveBeenCalledWith('repo-bad: quota reached');
  });

  it('refresh-activation only refreshes machine activation', async () => {
    await executeActivationRefresh('hostinger');

    expect(mockRefreshMachineActivation).toHaveBeenCalledTimes(1);
    expect(mockRefreshRepoLicensesBatch).not.toHaveBeenCalled();
    expect(mockOutputSuccess).toHaveBeenCalledWith('commands.subscription.refresh.refreshed');
  });

  it('refresh-repos only performs repo batch refresh', async () => {
    await executeRepoRefresh('hostinger');

    expect(mockRefreshMachineActivation).not.toHaveBeenCalled();
    expect(mockRefreshRepoLicensesBatch).toHaveBeenCalledTimes(1);
    expect(mockOutputSuccess).toHaveBeenCalledWith('commands.subscription.refresh.repos.success');
  });

  it('refresh fails when machine activation refresh is rejected', async () => {
    mockRefreshMachineActivation.mockResolvedValueOnce(false);

    await expect(executeSubscriptionRefresh('hostinger')).rejects.toThrow(
      'commands.subscription.refresh.failed'
    );
    expect(mockRefreshRepoLicensesBatch).not.toHaveBeenCalled();
  });

  it('renders repo batch summary including failures', () => {
    renderRepoBatchRefreshSummary({
      scanned: 2,
      issued: 1,
      refreshed: 0,
      unchanged: 1,
      failed: 1,
      valid: 2,
      failures: [{ repositoryGuid: 'repo-x', error: 'account quota reached' }],
    });

    expect(mockOutputInfo).toHaveBeenCalledWith(
      'Repo licenses: scanned 2, issued 1, refreshed 0, unchanged 1, failed 1'
    );
    expect(mockOutputWarn).toHaveBeenCalledWith('repo-x: account quota reached');
  });
});
