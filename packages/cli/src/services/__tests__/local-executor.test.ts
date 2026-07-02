import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  mockConnect,
  mockClose,
  mockExec,
  mockExecStreaming,
  mockGetLocalConfig,
  mockGetLocalMachine,
  mockGetRepository,
  mockListStorages,
  mockListRepositories,
  mockIssueRepoLicense,
  mockRefreshRepoLicensesBatch,
  mockRefreshRepoLicenseIdentity,
  mockAuthorizeSubscriptionViaDeviceCode,
  mockGetSubscriptionTokenState,
  mockBuildLocalVault,
  mockProvisionRenetToRemote,
  mockReadSSHKey,
  mockReadOptionalSSHKey,
  mockVerifyMachineSetup,
} = vi.hoisted(() => ({
  mockConnect: vi.fn(),
  mockClose: vi.fn(),
  mockExec: vi.fn(),
  mockExecStreaming: vi.fn(),
  mockGetLocalConfig: vi.fn(),
  mockGetLocalMachine: vi.fn(),
  mockGetRepository: vi.fn(),
  mockListStorages: vi.fn(),
  mockListRepositories: vi.fn(),
  mockIssueRepoLicense: vi.fn(),
  mockRefreshRepoLicensesBatch: vi.fn(),
  mockRefreshRepoLicenseIdentity: vi.fn(),
  mockAuthorizeSubscriptionViaDeviceCode: vi.fn(),
  mockGetSubscriptionTokenState: vi.fn(),
  mockBuildLocalVault: vi.fn(() => '{"vault":"ok"}'),
  mockProvisionRenetToRemote: vi.fn(() => ({ remotePath: '/usr/bin/renet', uploaded: false })),
  mockReadSSHKey: vi.fn(() => 'PRIVATE_KEY'),
  mockReadOptionalSSHKey: vi.fn(() => 'PUBLIC_KEY'),
  mockVerifyMachineSetup: vi.fn(),
}));

vi.mock('../../shared-desktop/sftp/index.js', () => ({
  SFTPClient: class MockSFTPClient {
    connect = mockConnect;
    close = mockClose;
    exec = mockExec;
    execStreaming = mockExecStreaming;
    isConnected = () => true;
  },
}));

vi.mock('../config-resources.js', () => ({
  configService: {
    getLocalConfig: mockGetLocalConfig,
    getLocalMachine: mockGetLocalMachine,
    getRepository: mockGetRepository,
    listStorages: mockListStorages,
    listRepositories: mockListRepositories,
  },
}));

vi.mock('../license.js', () => ({
  refreshRepoLicensesBatch: mockRefreshRepoLicensesBatch,
  issueRepoLicense: mockIssueRepoLicense,
  refreshRepoLicenseIdentity: mockRefreshRepoLicenseIdentity,
}));

vi.mock('../subscription-device-auth.js', () => ({
  authorizeSubscriptionViaDeviceCode: mockAuthorizeSubscriptionViaDeviceCode,
}));

vi.mock('../subscription-auth.js', () => ({
  getSubscriptionTokenState: mockGetSubscriptionTokenState,
}));

vi.mock('../../utils/agent-guard.js', () => ({
  isAgentEnvironment: vi.fn().mockReturnValue(false),
}));

vi.mock('../renet-execution.js', () => ({
  buildLocalVault: mockBuildLocalVault,
  provisionRenetToRemote: mockProvisionRenetToRemote,
  readSSHKey: mockReadSSHKey,
  readOptionalSSHKey: mockReadOptionalSSHKey,
  verifyMachineSetup: mockVerifyMachineSetup,
  getLocalRenetPath: vi.fn(),
}));

const { localExecutorService } = await import('../local-executor.js');

describe('localExecutorService first-use onboarding', () => {
  const savedSkipActivation = process.env.REDIACC_SKIP_MACHINE_ACTIVATION;

  beforeEach(() => {
    vi.clearAllMocks();
    delete process.env.REDIACC_SKIP_MACHINE_ACTIVATION;
    mockGetLocalConfig.mockResolvedValue({
      sshPrivateKey: 'PRIVATE_KEY',
      sshPublicKey: 'PUBLIC_KEY',
      ssh: {
        privateKeyPath: '/tmp/id',
        publicKeyPath: '/tmp/id.pub',
      },
    });
    mockGetLocalMachine.mockResolvedValue({
      machineName: 'hostinger',
      ip: '127.0.0.1',
      user: 'root',
      port: 22,
    });
    mockListStorages.mockResolvedValue([]);
    mockListRepositories.mockResolvedValue([]);
    mockIssueRepoLicense.mockResolvedValue(true);
    mockRefreshRepoLicensesBatch.mockResolvedValue({
      scanned: 1,
      issued: 1,
      refreshed: 0,
      unchanged: 0,
      failed: 0,
      valid: 1,
      invalidSignatureDetected: 0,
      failures: [],
      recoveryFailureMode: null,
      serverErrorSample: undefined,
    });
    mockAuthorizeSubscriptionViaDeviceCode.mockResolvedValue({
      storedToken: {
        token: 'rdt_test',
        serverUrl: 'http://localhost:4800',
      },
      status: { subscriptionId: 'sub_1' },
    });
    mockGetSubscriptionTokenState.mockReturnValue({ kind: 'missing' });
  });

  afterEach(() => {
    if (savedSkipActivation !== undefined) {
      process.env.REDIACC_SKIP_MACHINE_ACTIVATION = savedSkipActivation;
    }
  });

  it('authorizes and retries once on first-use missing-license failures', async () => {
    mockExecStreaming
      .mockImplementationOnce((_cmd: string, handlers: { onStderr?: (chunk: string) => void }) => {
        handlers.onStderr?.(
          '{"code":"LICENSE_REQUIRED","reason":"missing","message":"repo license required"}\n'
        );
        return Promise.resolve(10);
      })
      .mockImplementationOnce(() => Promise.resolve(0));

    const result = await localExecutorService.execute({
      functionName: 'backup_push',
      machineName: 'hostinger',
      captureOutput: true,
    });

    expect(mockAuthorizeSubscriptionViaDeviceCode).toHaveBeenCalledTimes(1);
    expect(mockRefreshRepoLicensesBatch).toHaveBeenCalledTimes(1);
    expect(mockExecStreaming).toHaveBeenCalledTimes(2);
    expect(result.success).toBe(true);
  });

  it('issues a license on missing-license recovery for operate-tier repository_up (rediacc/console#482)', async () => {
    // repository_up is on the pre-flight deny-list, but recovery after a
    // genuine missing-license failure on a fresh machine must still issue.
    mockExecStreaming
      .mockImplementationOnce((_cmd: string, handlers: { onStderr?: (chunk: string) => void }) => {
        handlers.onStderr?.(
          '{"code":"LICENSE_REQUIRED","reason":"missing","message":"no license data"}\n'
        );
        return Promise.resolve(10);
      })
      .mockImplementationOnce(() => Promise.resolve(0));

    const result = await localExecutorService.execute({
      functionName: 'repository_up',
      machineName: 'benchtest482',
      captureOutput: true,
    });

    expect(mockRefreshRepoLicensesBatch).toHaveBeenCalledTimes(1);
    expect(mockExecStreaming).toHaveBeenCalledTimes(2);
    expect(result.success).toBe(true);
  });

  it('surfaces server-rejected guidance when operate-tier recovery cannot issue', async () => {
    mockRefreshRepoLicensesBatch.mockResolvedValueOnce({
      scanned: 1,
      issued: 0,
      refreshed: 0,
      unchanged: 0,
      failed: 1,
      valid: 0,
      invalidSignatureDetected: 0,
      failures: [{ repositoryGuid: 'g', error: 'D1_ERROR: boom' }],
      recoveryFailureMode: 'server_rejected_all',
      serverErrorSample: 'D1_ERROR: boom',
    });
    mockExecStreaming.mockImplementationOnce(
      (_cmd: string, handlers: { onStderr?: (chunk: string) => void }) => {
        handlers.onStderr?.(
          '{"code":"LICENSE_REQUIRED","reason":"missing","message":"no license data"}\n'
        );
        return Promise.resolve(10);
      }
    );

    const result = await localExecutorService.execute({
      functionName: 'repository_up',
      machineName: 'benchtest482',
      captureOutput: true,
    });

    expect(mockRefreshRepoLicensesBatch).toHaveBeenCalledTimes(1);
    expect(result.success).toBe(false);
    expect(result.error).toContain('D1_ERROR: boom');
  });

  it('does not authorize when the license-required reason is not missing', async () => {
    mockExecStreaming
      .mockImplementationOnce((_cmd: string, handlers: { onStderr?: (chunk: string) => void }) => {
        handlers.onStderr?.(
          '{"code":"LICENSE_REQUIRED","reason":"expired","message":"repo license required"}\n'
        );
        return Promise.resolve(10);
      })
      .mockImplementationOnce(() => Promise.resolve(0));

    const result = await localExecutorService.execute({
      functionName: 'backup_push',
      machineName: 'hostinger',
      captureOutput: true,
    });

    expect(mockAuthorizeSubscriptionViaDeviceCode).not.toHaveBeenCalled();
    expect(mockRefreshRepoLicensesBatch).toHaveBeenCalledTimes(1);
    expect(mockExecStreaming).toHaveBeenCalledTimes(2);
    expect(result.success).toBe(true);
  });

  it('fails fast on machine mismatch without refreshing', async () => {
    mockExecStreaming.mockImplementationOnce(
      (_cmd: string, handlers: { onStderr?: (chunk: string) => void }) => {
        handlers.onStderr?.(
          '{"code":"LICENSE_REQUIRED","reason":"machine_mismatch","message":"repo license required"}\n'
        );
        return Promise.resolve(10);
      }
    );

    const result = await localExecutorService.execute({
      functionName: 'backup_push',
      machineName: 'hostinger',
      captureOutput: true,
    });

    expect(mockAuthorizeSubscriptionViaDeviceCode).not.toHaveBeenCalled();
    expect(mockIssueRepoLicense).not.toHaveBeenCalled();
    expect(mockRefreshRepoLicensesBatch).not.toHaveBeenCalled();
    expect(mockExecStreaming).toHaveBeenCalledTimes(1);
    expect(result.success).toBe(false);
    expect(result.errorCode).toBe('REPO_LICENSE_MACHINE_MISMATCH');
    expect(result.error).toContain('belongs to a different machine');
  });

  it('fails fast on repository mismatch without refreshing', async () => {
    mockExecStreaming.mockImplementationOnce(
      (_cmd: string, handlers: { onStderr?: (chunk: string) => void }) => {
        handlers.onStderr?.(
          '{"code":"LICENSE_REQUIRED","reason":"repository_mismatch","message":"repo license required"}\n'
        );
        return Promise.resolve(10);
      }
    );

    const result = await localExecutorService.execute({
      functionName: 'backup_push',
      machineName: 'hostinger',
      captureOutput: true,
    });

    expect(mockIssueRepoLicense).not.toHaveBeenCalled();
    expect(mockRefreshRepoLicensesBatch).not.toHaveBeenCalled();
    expect(result.success).toBe(false);
    expect(result.errorCode).toBe('REPO_LICENSE_REPOSITORY_MISMATCH');
    expect(result.error).toContain('does not match the target repository');
  });

  it('fails fast on sequence regression without refreshing', async () => {
    mockExecStreaming.mockImplementationOnce(
      (_cmd: string, handlers: { onStderr?: (chunk: string) => void }) => {
        handlers.onStderr?.(
          '{"code":"LICENSE_REQUIRED","reason":"sequence_regression","message":"repo license required"}\n'
        );
        return Promise.resolve(10);
      }
    );

    const result = await localExecutorService.execute({
      functionName: 'backup_push',
      machineName: 'hostinger',
      captureOutput: true,
    });

    expect(mockIssueRepoLicense).not.toHaveBeenCalled();
    expect(mockRefreshRepoLicensesBatch).not.toHaveBeenCalled();
    expect(result.success).toBe(false);
    expect(result.errorCode).toBe('REPO_LICENSE_INTEGRITY_ERROR');
    expect(result.error).toContain('older than the latest accepted sequence');
  });

  it('fails fast on invalid signature without refreshing', async () => {
    mockExecStreaming.mockImplementationOnce(
      (_cmd: string, handlers: { onStderr?: (chunk: string) => void }) => {
        handlers.onStderr?.(
          '{"code":"LICENSE_REQUIRED","reason":"invalid_signature","message":"repo license required"}\n'
        );
        return Promise.resolve(10);
      }
    );

    const result = await localExecutorService.execute({
      functionName: 'backup_push',
      machineName: 'hostinger',
      captureOutput: true,
    });

    expect(mockIssueRepoLicense).not.toHaveBeenCalled();
    expect(mockRefreshRepoLicensesBatch).not.toHaveBeenCalled();
    expect(result.success).toBe(false);
    expect(result.errorCode).toBe('REPO_LICENSE_INTEGRITY_ERROR');
    expect(result.error).toContain('could not be trusted');
  });

  it('fails fast on identity mismatch without refreshing', async () => {
    mockExecStreaming.mockImplementationOnce(
      (_cmd: string, handlers: { onStderr?: (chunk: string) => void }) => {
        handlers.onStderr?.(
          '{"code":"LICENSE_REQUIRED","reason":"identity_mismatch","message":"repo identity mismatch"}\n'
        );
        return Promise.resolve(10);
      }
    );

    const result = await localExecutorService.execute({
      functionName: 'backup_push',
      machineName: 'hostinger',
      captureOutput: true,
    });

    expect(mockIssueRepoLicense).not.toHaveBeenCalled();
    expect(mockRefreshRepoLicensesBatch).not.toHaveBeenCalled();
    expect(result.success).toBe(false);
    expect(result.errorCode).toBe('REPO_LICENSE_IDENTITY_MISMATCH');
    expect(result.error).toContain('repository identity does not match');
  });

  it('reports server_rejected_all message when recovery returns no valid licenses', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({ kind: 'ready', token: { token: 'rdt_test' } });
    mockRefreshRepoLicensesBatch.mockResolvedValueOnce({
      scanned: 1,
      issued: 0,
      refreshed: 0,
      unchanged: 0,
      failed: 1,
      valid: 0,
      invalidSignatureDetected: 0,
      failures: [{ repositoryGuid: 'abc-123', error: 'quota exceeded for plan' }],
      recoveryFailureMode: 'server_rejected_all',
      serverErrorSample: 'quota exceeded for plan',
    });
    mockExecStreaming.mockImplementationOnce(
      (_cmd: string, handlers: { onStderr?: (chunk: string) => void }) => {
        handlers.onStderr?.(
          '{"code":"LICENSE_REQUIRED","reason":"missing","message":"repo license required"}\n'
        );
        return Promise.resolve(10);
      }
    );

    const result = await localExecutorService.execute({
      functionName: 'backup_push',
      machineName: 'hostinger',
      captureOutput: true,
    });

    expect(result.success).toBe(false);
    expect(result.errorCode).toBe('REPO_LICENSE_ISSUANCE_REQUIRED');
    expect(result.error).toContain('quota exceeded for plan');
  });

  it('reports token_not_ready guidance when recovery is blocked by missing token', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({ kind: 'ready', token: { token: 'rdt_test' } });
    mockRefreshRepoLicensesBatch.mockResolvedValueOnce({
      scanned: 0,
      issued: 0,
      refreshed: 0,
      unchanged: 0,
      failed: 0,
      valid: 0,
      invalidSignatureDetected: 0,
      failures: [{ repositoryGuid: '*', error: 'Subscription token is not ready' }],
      recoveryFailureMode: 'token_not_ready',
      serverErrorSample: undefined,
    });
    mockExecStreaming.mockImplementationOnce(
      (_cmd: string, handlers: { onStderr?: (chunk: string) => void }) => {
        handlers.onStderr?.(
          '{"code":"LICENSE_REQUIRED","reason":"missing","message":"repo license required"}\n'
        );
        return Promise.resolve(10);
      }
    );

    const result = await localExecutorService.execute({
      functionName: 'backup_push',
      machineName: 'hostinger',
      captureOutput: true,
    });

    expect(result.success).toBe(false);
    expect(result.errorCode).toBe('REPO_LICENSE_ISSUANCE_REQUIRED');
    expect(result.error).toContain('rdc subscription login');
  });

  it('reports no_known_repos guidance when recovery cannot match repos to local config', async () => {
    mockGetSubscriptionTokenState.mockReturnValue({ kind: 'ready', token: { token: 'rdt_test' } });
    mockRefreshRepoLicensesBatch.mockResolvedValueOnce({
      scanned: 2,
      issued: 0,
      refreshed: 0,
      unchanged: 0,
      failed: 2,
      valid: 0,
      invalidSignatureDetected: 0,
      failures: [
        {
          repositoryGuid: 'abc-001',
          error: 'Repository exists on target machine but is not tracked in local config',
        },
        {
          repositoryGuid: 'abc-002',
          error: 'Repository exists on target machine but is not tracked in local config',
        },
      ],
      recoveryFailureMode: 'no_known_repos',
      serverErrorSample: undefined,
    });
    mockExecStreaming.mockImplementationOnce(
      (_cmd: string, handlers: { onStderr?: (chunk: string) => void }) => {
        handlers.onStderr?.(
          '{"code":"LICENSE_REQUIRED","reason":"missing","message":"repo license required"}\n'
        );
        return Promise.resolve(10);
      }
    );

    const result = await localExecutorService.execute({
      functionName: 'backup_push',
      machineName: 'hostinger',
      captureOutput: true,
    });

    expect(result.success).toBe(false);
    expect(result.errorCode).toBe('REPO_LICENSE_ISSUANCE_REQUIRED');
    expect(result.error).toContain('tracked in your local config');
  });
});

describe('localExecutorService create/fork licensing flow', () => {
  const savedSkipActivation = process.env.REDIACC_SKIP_MACHINE_ACTIVATION;

  beforeEach(() => {
    vi.clearAllMocks();
    delete process.env.REDIACC_SKIP_MACHINE_ACTIVATION;
    mockGetLocalConfig.mockResolvedValue({
      sshPrivateKey: 'PRIVATE_KEY',
      sshPublicKey: 'PUBLIC_KEY',
      ssh: {
        privateKeyPath: '/tmp/id',
        publicKeyPath: '/tmp/id.pub',
      },
    });
    mockGetLocalMachine.mockResolvedValue({
      machineName: 'hostinger',
      ip: '127.0.0.1',
      user: 'root',
      port: 22,
    });
    mockGetRepository.mockResolvedValue({ repositoryGuid: 'guid-1' });
    mockListStorages.mockResolvedValue([]);
    mockListRepositories.mockResolvedValue([]);
    mockIssueRepoLicense.mockResolvedValue(true);
    mockRefreshRepoLicenseIdentity.mockResolvedValue(true);
    mockGetSubscriptionTokenState.mockReturnValue({ kind: 'ready', token: { token: 'rdt_test' } });
    mockExecStreaming.mockResolvedValue(0);
  });

  afterEach(() => {
    if (savedSkipActivation !== undefined) {
      process.env.REDIACC_SKIP_MACHINE_ACTIVATION = savedSkipActivation;
    }
  });

  const createOptions = {
    functionName: 'repository_create',
    machineName: 'hostinger',
    params: { repository: 'myrepo', size: '1G' },
    captureOutput: true,
  };

  it('refreshes repo identity after a successful create by default', async () => {
    const result = await localExecutorService.execute(createOptions);

    expect(result.success).toBe(true);
    expect(mockRefreshRepoLicenseIdentity).toHaveBeenCalledTimes(1);
    // The shared SFTP session is passed through to license issuance.
    expect(mockRefreshRepoLicenseIdentity.mock.calls[0][4]).toBeDefined();
  });

  it('skips the identity refresh when deferIdentityRefresh is set', async () => {
    const result = await localExecutorService.execute({
      ...createOptions,
      deferIdentityRefresh: true,
    });

    expect(result.success).toBe(true);
    expect(mockRefreshRepoLicenseIdentity).not.toHaveBeenCalled();
  });

  it('runs machine verification concurrently with license issuance', async () => {
    const events: string[] = [];
    mockVerifyMachineSetup.mockImplementation(async () => {
      events.push('verify_start');
      await new Promise((resolve) => setTimeout(resolve, 25));
      events.push('verify_end');
    });
    mockIssueRepoLicense.mockImplementation(() => {
      events.push('license_start');
      return Promise.resolve(true);
    });

    const result = await localExecutorService.execute(createOptions);

    expect(result.success).toBe(true);
    // With sequential execution, license_start would come after verify_end.
    expect(events.indexOf('license_start')).toBeGreaterThan(events.indexOf('verify_start'));
    expect(events.indexOf('license_start')).toBeLessThan(events.indexOf('verify_end'));
  });

  it('populates cliSteps on the result alongside allSteps', async () => {
    const result = await localExecutorService.execute(createOptions);

    expect(result.success).toBe(true);
    const names = (result.cliSteps ?? []).map((s) => s.name);
    expect(names).toEqual(
      expect.arrayContaining([
        'config',
        'ssh_connect',
        'renet_provision',
        'machine_verify',
        'license',
      ])
    );
    for (const step of result.cliSteps ?? []) {
      expect(result.allSteps).toContainEqual(step);
    }
  });

  it('refreshIdentityFor acquires a pooled connection and shares it with licensing', async () => {
    await localExecutorService.refreshIdentityFor('repository_create', 'hostinger', {
      repository: 'myrepo',
      size: '1G',
    });

    expect(mockRefreshRepoLicenseIdentity).toHaveBeenCalledTimes(1);
    const call = mockRefreshRepoLicenseIdentity.mock.calls[0];
    expect(call[1]).toBe('PRIVATE_KEY');
    expect(call[2]).toMatchObject({ repositoryGuid: 'guid-1', kind: 'grand' });
    expect(call[4]).toBeDefined();
    // The lease was released, dropping the last reference and closing.
    expect(mockClose).toHaveBeenCalledTimes(1);
  });

  it('refreshIdentityFor is a no-op when machine activation is skipped', async () => {
    process.env.REDIACC_SKIP_MACHINE_ACTIVATION = '1';
    await localExecutorService.refreshIdentityFor('repository_create', 'hostinger', {
      repository: 'myrepo',
    });
    expect(mockConnect).not.toHaveBeenCalled();
    expect(mockRefreshRepoLicenseIdentity).not.toHaveBeenCalled();
  });
});
