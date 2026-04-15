import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  mockConnect,
  mockClose,
  mockExec,
  mockExecStreaming,
  mockGetLocalConfig,
  mockGetLocalMachine,
  mockListStorages,
  mockListRepositories,
  mockIssueRepoLicense,
  mockRefreshRepoLicensesBatch,
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
  mockListStorages: vi.fn(),
  mockListRepositories: vi.fn(),
  mockIssueRepoLicense: vi.fn(),
  mockRefreshRepoLicensesBatch: vi.fn(),
  mockAuthorizeSubscriptionViaDeviceCode: vi.fn(),
  mockGetSubscriptionTokenState: vi.fn(),
  mockBuildLocalVault: vi.fn(() => '{"vault":"ok"}'),
  mockProvisionRenetToRemote: vi.fn(() => ({ remotePath: '/usr/bin/renet', uploaded: false })),
  mockReadSSHKey: vi.fn(() => 'PRIVATE_KEY'),
  mockReadOptionalSSHKey: vi.fn(() => 'PUBLIC_KEY'),
  mockVerifyMachineSetup: vi.fn(),
}));

vi.mock('@rediacc/shared-desktop/sftp', () => ({
  SFTPClient: class MockSFTPClient {
    connect = mockConnect;
    close = mockClose;
    exec = mockExec;
    execStreaming = mockExecStreaming;
  },
}));

vi.mock('../config-resources.js', () => ({
  configService: {
    getLocalConfig: mockGetLocalConfig,
    getLocalMachine: mockGetLocalMachine,
    listStorages: mockListStorages,
    listRepositories: mockListRepositories,
  },
}));

vi.mock('../license.js', () => ({
  refreshRepoLicensesBatch: mockRefreshRepoLicensesBatch,
  issueRepoLicense: mockIssueRepoLicense,
  refreshRepoLicenseIdentity: vi.fn(),
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
});
