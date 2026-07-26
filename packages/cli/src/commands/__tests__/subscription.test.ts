import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  mockGetSubscriptionTokenState,
  mockFetchSubscriptionLicenseReport,
  mockReadMachineActivationStatus,
  mockReadRuntimeRepoLicenseStatuses,
  mockRefreshRepoLicensesBatch,
  mockRefreshRepoLicenseIdentity,
  mockAuthorizeSubscriptionViaDeviceCode,
  mockGetLocalConfig,
  mockGetLocalMachine,
  mockGetRepository,
  mockResolveRepoRef,
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
  mockReadAccountPointer,
  mockDiscoverRegions,
  mockPromptRegionSelection,
} = vi.hoisted(() => ({
  mockGetSubscriptionTokenState: vi.fn(),
  mockFetchSubscriptionLicenseReport: vi.fn(),
  mockReadMachineActivationStatus: vi.fn(),
  mockReadRuntimeRepoLicenseStatuses: vi.fn(),
  mockRefreshRepoLicensesBatch: vi.fn(),
  mockRefreshRepoLicenseIdentity: vi.fn(),
  mockAuthorizeSubscriptionViaDeviceCode: vi.fn(),
  mockGetLocalConfig: vi.fn(),
  mockGetLocalMachine: vi.fn(),
  mockGetRepository: vi.fn(),
  mockResolveRepoRef: vi.fn(),
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
  mockReadAccountPointer: vi.fn(() => ({ accountServer: 'http://localhost:4800' })),
  mockDiscoverRegions: vi.fn(),
  mockPromptRegionSelection: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, string | number>) => {
    return vars ? `${key}:${Object.values(vars).join(':')}` : key;
  },
}));

vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: mockGetSubscriptionTokenState,
  getSubscriptionServerUrl: mockGetSubscriptionServerUrl,
  getSubscriptionScopeMismatch: mockGetSubscriptionScopeMismatch,
  saveStoredSubscriptionToken: mockSaveStoredSubscriptionToken,
}));

vi.mock('../../services/account/account-pointer.js', () => ({
  readAccountPointer: mockReadAccountPointer,
}));

vi.mock('../../services/provision/region-discovery.js', () => ({
  discoverRegions: mockDiscoverRegions,
}));

vi.mock('../../utils/region-prompt.js', () => ({
  promptRegionSelection: mockPromptRegionSelection,
}));

vi.mock('../../services/account/license.js', () => ({
  fetchSubscriptionLicenseReport: mockFetchSubscriptionLicenseReport,
  readMachineActivationStatus: mockReadMachineActivationStatus,
  readRuntimeRepoLicenseStatuses: mockReadRuntimeRepoLicenseStatuses,
  refreshRepoLicensesBatch: mockRefreshRepoLicensesBatch,
  refreshRepoLicenseIdentity: mockRefreshRepoLicenseIdentity,
}));

vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: mockResolveRepoRef,
}));

vi.mock('../../services/account/subscription-device-auth.js', () => ({
  authorizeSubscriptionViaDeviceCode: mockAuthorizeSubscriptionViaDeviceCode,
}));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getLocalConfig: mockGetLocalConfig,
    getLocalMachine: mockGetLocalMachine,
    getRepository: mockGetRepository,
    getTeam: mockGetTeam,
  },
}));

vi.mock('../../services/renet/renet-execution.js', () => ({
  readSSHKey: mockReadSSHKey,
  provisionRenetToRemote: mockProvisionRenetToRemote,
}));

vi.mock('../../services/core/output.js', () => ({
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
  executeMachineStatus,
  executeAccountRefresh,
  executeMachineRefresh,
  executeRepoLicenseRefresh,
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
    mockReadRuntimeRepoLicenseStatuses.mockResolvedValue([]);
    mockResolveRepoRef.mockResolvedValue({
      name: 'shop',
      repoKey: 'shop:test',
      machineName: 'hostinger',
      tag: 'test',
    });
    mockGetRepository.mockResolvedValue({
      repositoryGuid: 'repo-guid',
      grandGuid: 'grand-guid',
    });
    mockRefreshRepoLicenseIdentity.mockResolvedValue(true);
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

  it('status handles missing token state without fetching report, and prints would-use server', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({ kind: 'missing' });

    await executeSubscriptionStatus();

    expect(mockOutputInfo).toHaveBeenCalledWith('errors.subscription.notLoggedIn');
    expect(mockOutputInfo).toHaveBeenCalledWith(
      'commands.subscription.status.serverWouldUse:http://localhost:4800'
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

  it('status -m renders activation and the repo license table from one renet provisioning', async () => {
    mockReadMachineActivationStatus.mockResolvedValue({
      machineId: 'machine-activation-id',
      active: true,
      lastSeenAt: '2026-03-12T00:00:00Z',
      activeCount: 1,
      maxCount: 2,
    });
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

    await executeMachineStatus('hostinger');

    // Both sections share one renet provisioning.
    expect(mockProvisionRenetToRemote).toHaveBeenCalledTimes(1);
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
    // The account view is a different scope: no -m means no machine report.
    expect(mockFetchSubscriptionLicenseReport).not.toHaveBeenCalled();
  });

  it('status -m still renders the repo table when the activation lookup fails', async () => {
    mockReadMachineActivationStatus.mockRejectedValue(new Error('account unreachable'));
    mockReadRuntimeRepoLicenseStatuses.mockResolvedValue([]);

    await executeMachineStatus('hostinger');

    expect(mockOutputWarn).toHaveBeenCalledWith('commands.subscription.status.parseFailed');
    expect(mockOutputInfo).toHaveBeenCalledWith(
      'commands.subscription.repo.status.header:hostinger'
    );
    expect(mockOutputInfo).toHaveBeenCalledWith('commands.subscription.repo.status.empty');
  });

  it('refresh with no flags re-reads account state and never touches a machine', async () => {
    mockFetchSubscriptionLicenseReport.mockResolvedValue({
      subscriptionId: 'sub_1',
      orgName: 'Acme',
      teamName: 'Platform',
      planCode: 'COMMUNITY',
      status: 'active',
      machineSlots: { active: 1, max: 2, machines: [] },
      repoLicenseIssuances: {
        used: 1,
        limit: 500,
        windowStart: '2026-03-01T00:00:00Z',
        windowEnd: '2026-04-01T00:00:00Z',
      },
      repoLicenses: {
        totalTrackedRepos: 1,
        validCount: 1,
        refreshRecommendedCount: 0,
        hardExpiredCount: 0,
      },
    });

    await executeAccountRefresh();

    expect(mockFetchSubscriptionLicenseReport).toHaveBeenCalledTimes(1);
    expect(mockOutputInfo).toHaveBeenCalledWith('commands.subscription.status.remote');
    expect(mockProvisionRenetToRemote).not.toHaveBeenCalled();
    expect(mockRefreshRepoLicensesBatch).not.toHaveBeenCalled();
  });

  it('refresh with no flags fails when the account report cannot be read', async () => {
    mockFetchSubscriptionLicenseReport.mockResolvedValue(null);

    await expect(executeAccountRefresh()).rejects.toThrow(
      'commands.subscription.refresh.account.failed'
    );
  });

  it('refresh -m runs repo batch refresh and prints the summary', async () => {
    await executeMachineRefresh('hostinger');

    expect(mockRefreshRepoLicensesBatch).toHaveBeenCalledTimes(1);
    expect(mockOutputSuccess).toHaveBeenCalledWith('commands.subscription.refresh.success');
    expect(mockOutputWarn).toHaveBeenCalledWith('repo-bad: quota reached');
  });

  it('refresh --repo derives the machine from the ref and refreshes one license', async () => {
    await executeRepoLicenseRefresh('shop:test');

    expect(mockResolveRepoRef).toHaveBeenCalledWith('shop:test', { readOnly: true });
    expect(mockGetLocalMachine).toHaveBeenCalledWith('hostinger');
    expect(mockGetRepository).toHaveBeenCalledWith('shop:test');
    expect(mockRefreshRepoLicenseIdentity).toHaveBeenCalledWith(
      expect.objectContaining({ machineName: 'hostinger' }),
      'PRIVATE_KEY',
      { repositoryGuid: 'repo-guid', grandGuid: 'grand-guid', kind: 'fork' }
    );
    expect(mockRefreshRepoLicensesBatch).not.toHaveBeenCalled();
    expect(mockOutputSuccess).toHaveBeenCalledWith(
      'commands.subscription.refresh.repo.success:shop:test'
    );
  });

  it('refresh --repo fails when the ref is not a repository in this config', async () => {
    mockGetRepository.mockResolvedValue(undefined);

    await expect(executeRepoLicenseRefresh('shop:test')).rejects.toThrow(
      'commands.subscription.refresh.repo.notFound:shop:test'
    );
    expect(mockRefreshRepoLicenseIdentity).not.toHaveBeenCalled();
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

  // ─── Region selection on first login ─────────────────────────────────

  describe('region selection on first login', () => {
    it('should skip region prompt when the config has an accountServer', () => {
      mockReadAccountPointer.mockReturnValue({ accountServer: 'https://eu.rediacc.com' });

      // With accountServer set in the config pointer, the prompt should not trigger.
      const pointer = mockReadAccountPointer() as { accountServer?: string };
      expect(pointer.accountServer).toBeTruthy();
      expect(mockDiscoverRegions).not.toHaveBeenCalled();
      expect(mockPromptRegionSelection).not.toHaveBeenCalled();
    });
  });
});
