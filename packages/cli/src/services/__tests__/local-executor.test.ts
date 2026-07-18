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

vi.mock('../../remote/sftp/index.js', () => ({
  SFTPClient: class MockSFTPClient {
    connect = mockConnect;
    close = mockClose;
    exec = mockExec;
    execStreaming = mockExecStreaming;
    isConnected = () => true;
  },
}));

vi.mock('../config/config-resources.js', () => ({
  configService: {
    getLocalConfig: mockGetLocalConfig,
    getLocalMachine: mockGetLocalMachine,
    getRepository: mockGetRepository,
    listStorages: mockListStorages,
    listRepositories: mockListRepositories,
  },
}));

vi.mock('../account/license.js', () => ({
  refreshRepoLicensesBatch: mockRefreshRepoLicensesBatch,
  issueRepoLicense: mockIssueRepoLicense,
  refreshRepoLicenseIdentity: mockRefreshRepoLicenseIdentity,
}));

vi.mock('../account/subscription-device-auth.js', () => ({
  authorizeSubscriptionViaDeviceCode: mockAuthorizeSubscriptionViaDeviceCode,
}));

vi.mock('../account/subscription-auth.js', () => ({
  getSubscriptionTokenState: mockGetSubscriptionTokenState,
}));

vi.mock('../../utils/agent-guard.js', () => ({
  isAgentEnvironment: vi.fn().mockReturnValue(false),
}));

vi.mock('../renet/renet-execution.js', () => ({
  buildLocalVault: mockBuildLocalVault,
  provisionRenetToRemote: mockProvisionRenetToRemote,
  readSSHKey: mockReadSSHKey,
  readOptionalSSHKey: mockReadOptionalSSHKey,
  verifyMachineSetup: mockVerifyMachineSetup,
  getLocalRenetPath: vi.fn(),
}));

const { localExecutorService } = await import('../executor/local-executor.js');

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

  // Bug #46: `kubeCluster` used to ALSO rewrite machineName to the cluster's
  // control node. KUBECONFIG is the k8s analog of DOCKER_HOST, and DOCKER_HOST
  // never reroutes the machine either: the caller's derived machine must stand,
  // or every volume-level op on a k8s repo (trim, diff, commit, repo up's LUKS
  // mount) runs on the control node instead of the host that mounts the datastore.
  describe('bug #46: kubeCluster injects KUBECONFIG but never reroutes the machine', () => {
    it('runs on the caller-derived machine (the datastore attach host), not the control node', async () => {
      mockExecStreaming.mockImplementationOnce(() => Promise.resolve(0));

      await localExecutorService.execute({
        functionName: 'repository_trim',
        // What resolveRepoRef derives: state.datastores[D].attachedTo. This is a
        // WORKER, deliberately not the cluster's control node.
        machineName: 'worker-1',
        kubeCluster: 'c1',
        captureOutput: true,
      });

      expect(mockGetLocalMachine).toHaveBeenCalledWith('worker-1');
      expect(mockGetLocalMachine).not.toHaveBeenCalledWith('c1-cp-1');
    });

    it('still injects KUBECONFIG for the cluster while running on that machine', async () => {
      mockExecStreaming.mockImplementationOnce(() => Promise.resolve(0));

      await localExecutorService.execute({
        functionName: 'repository_up',
        machineName: 'worker-1',
        kubeCluster: 'c1',
        captureOutput: true,
      });

      const command = mockExecStreaming.mock.calls.at(-1)?.[0] as string;
      expect(command).toContain('KUBECONFIG=');
      expect(command).toContain('c1');
      expect(mockGetLocalMachine).toHaveBeenCalledWith('worker-1');
    });

    it('a cluster-scoped op still reaches the control node, because its CALL SITE says so', async () => {
      // services/cluster/* already resolve the control node explicitly
      // (resolveExecutionTarget({ cluster }) -> machineName: control). That is the
      // sanctioned way to run FROM the control node: explicit, not ambient.
      mockExecStreaming.mockImplementationOnce(() => Promise.resolve(0));

      await localExecutorService.execute({
        functionName: 'kube_node_remove',
        machineName: 'c1-cp-1',
        kubeCluster: 'c1',
        captureOutput: true,
      });

      expect(mockGetLocalMachine).toHaveBeenCalledWith('c1-cp-1');
    });
  });

  // ── #74: the datastore CHANNEL ────────────────────────────────────────────
  //
  // renet reads the datastore from the MACHINE VAULT (`p.Datastore()` ->
  // `machineDatastore`, set only by `WithMachineVault`), which the executor builds
  // from the config machine record. `repository_create` calls `AddDatastore`, which
  // reads that vault — NOT the params bag. (The kube_* verbs DO read a `datastore`
  // param, which is exactly how a caller comes to believe the param is heard: the
  // same name is live on one verb and inert on another.)
  //
  // So a repo on a NAMED datastore had no way to say where it lived, and every
  // dispatch silently used the machine's default docker datastore instead.
  //
  // ★ THIS IS THE TEST THAT MAKES AN INERT FIX IMPOSSIBLE. It asks the CALLEE what
  // it will accept, not the caller what it meant to send: it asserts the executor
  // actually threads ExecuteOptions.datastore into the machine record handed to the
  // vault builder — the one field renet ever reads. A test that only checked that
  // some command set `params.datastore` would pass while the wire carried the wrong
  // datastore, which is precisely the bug this guards.
  describe('datastore override (#74)', () => {
    it('threads options.datastore into the machine record the vault is built from', async () => {
      await localExecutorService.execute({
        functionName: 'repository_create',
        machineName: 'hostinger',
        datastore: '/mnt/rediacc-ds/pds3',
        params: { repository: 'shop' },
      });

      expect(mockBuildLocalVault).toHaveBeenCalledTimes(1);
      const opts = mockBuildLocalVault.mock.calls[0][0] as { machine: { datastore?: string } };
      expect(opts.machine.datastore).toBe('/mnt/rediacc-ds/pds3');
    });

    it('leaves the machine default intact when no datastore is declared', async () => {
      // The fallback is CORRECT for a machine with no named datastore, and #74 is
      // that the caller stayed silent — not that the default exists. A caller that
      // declares nothing must still get the machine's own datastore.
      mockGetLocalMachine.mockResolvedValue({
        machineName: 'hostinger',
        ip: '127.0.0.1',
        user: 'root',
        port: 22,
        datastore: '/mnt/rediacc',
      });

      await localExecutorService.execute({
        functionName: 'repository_create',
        machineName: 'hostinger',
        params: { repository: 'shop' },
      });

      const opts = mockBuildLocalVault.mock.calls[0][0] as { machine: { datastore?: string } };
      expect(opts.machine.datastore).toBe('/mnt/rediacc');
    });
  });

  describe('passthroughOutput (repo exec / repo logs / run)', () => {
    /** Capture what the executor writes to stdout without polluting the test run. */
    function captureStdout(): { lines: () => string[]; restore: () => void } {
      const written: string[] = [];
      const spy = vi
        .spyOn(process.stdout, 'write')
        .mockImplementation((chunk: string | Uint8Array): boolean => {
          written.push(typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString());
          return true;
        });
      return { lines: () => written, restore: () => spy.mockRestore() };
    }

    function streamStdout(chunks: string[], exitCode = 0): void {
      mockExecStreaming.mockImplementationOnce(
        (_cmd: string, handlers: { onStdout?: (chunk: string) => void }) => {
          for (const chunk of chunks) handlers.onStdout?.(chunk);
          return Promise.resolve(exitCode);
        }
      );
    }

    it('prints the inner process output with the relay prefix stripped', async () => {
      streamStdout(['[container_exec] hello\n[container_exec] world\n']);
      const out = captureStdout();
      await localExecutorService.execute({
        functionName: 'container_exec',
        machineName: 'hostinger',
        passthroughOutput: true,
      });
      out.restore();
      expect(out.lines().join('')).toBe('hello\nworld\n');
    });

    it('drops renet logrus lines but keeps program output', async () => {
      streamStdout([
        'time="2026-07-18T19:09:33Z" level=info msg="Starting Go executor operation"\n',
        '[container_exec] real output\n',
      ]);
      const out = captureStdout();
      await localExecutorService.execute({
        functionName: 'container_exec',
        machineName: 'hostinger',
        passthroughOutput: true,
      });
      out.restore();
      expect(out.lines().join('')).toBe('real output\n');
    });

    it('reassembles a line split across chunks', async () => {
      // What `repo logs --follow` depends on: a socket read can split mid-line, and
      // a handler that printed per-chunk would tear the line in half.
      streamStdout(['[container_logs] li', 'ne1\n']);
      const out = captureStdout();
      await localExecutorService.execute({
        functionName: 'container_logs',
        machineName: 'hostinger',
        passthroughOutput: true,
      });
      out.restore();
      expect(out.lines().join('')).toBe('line1\n');
    });

    it('emits a final line that arrived without a trailing newline', async () => {
      streamStdout(['[container_exec] no trailing newline']);
      const out = captureStdout();
      await localExecutorService.execute({
        functionName: 'container_exec',
        machineName: 'hostinger',
        passthroughOutput: true,
      });
      out.restore();
      expect(out.lines().join('')).toBe('no trailing newline\n');
    });

    it('suppresses step events so they cannot poison captured output', async () => {
      streamStdout([
        '{"step_done":{"name":"provisioning","duration_ms":12}}\n[container_exec] ok\n',
      ]);
      const out = captureStdout();
      await localExecutorService.execute({
        functionName: 'container_exec',
        machineName: 'hostinger',
        passthroughOutput: true,
      });
      out.restore();
      expect(out.lines().join('')).toBe('ok\n');
    });

    it('keeps JSON container logs, which the failure-path cleaner would drop', async () => {
      streamStdout(['[container_logs] {"level":"info","msg":"app started"}\n']);
      const out = captureStdout();
      await localExecutorService.execute({
        functionName: 'container_logs',
        machineName: 'hostinger',
        passthroughOutput: true,
      });
      out.restore();
      expect(out.lines().join('')).toBe('{"level":"info","msg":"app started"}\n');
    });

    it('stays silent without the opt-in, so other commands are unchanged', async () => {
      streamStdout(['[repository_up] noisy renet chatter\n']);
      const out = captureStdout();
      await localExecutorService.execute({
        functionName: 'repository_up',
        machineName: 'hostinger',
      });
      out.restore();
      expect(out.lines().join('')).toBe('');
    });
  });

  describe("refusals survive the executor's catch-all", () => {
    it('rethrows a CliExitError instead of flattening it to exit 1', async () => {
      // The catch-all turns a thrown error into {success:false, exitCode:1}. That
      // is right for an execution failure and WRONG for a deliberate refusal: a
      // BUSY provisioning-lock timeout reached the user as an anonymous exit 1,
      // losing its code, its retryable flag and its "here is the pid" next-action.
      const { busy } = await import('../../utils/cli-exit-error.js');
      const { CliExitError } = await import('../../utils/cli-exit-error.js');
      mockProvisionRenetToRemote.mockImplementationOnce(() => {
        throw busy('Another rdc process is still provisioning renet', {
          details: ['Lock: /tmp/x.lock'],
        });
      });

      const thrown = await localExecutorService
        .execute({ functionName: 'repository_up', machineName: 'hostinger' })
        .then(() => null)
        .catch((e: unknown) => e);

      expect(thrown).toBeInstanceOf(CliExitError);
      expect((thrown as InstanceType<typeof CliExitError>).code).toBe('BUSY');
      expect((thrown as InstanceType<typeof CliExitError>).exitCode).toBe(15);
      expect((thrown as InstanceType<typeof CliExitError>).retryable).toBe(true);
    });

    it('still flattens an ordinary execution failure into a result', async () => {
      mockProvisionRenetToRemote.mockImplementationOnce(() => {
        throw new Error('ssh blew up');
      });

      const result = await localExecutorService.execute({
        functionName: 'repository_up',
        machineName: 'hostinger',
      });

      expect(result.success).toBe(false);
      expect(result.exitCode).toBe(1);
      expect(result.error).toContain('ssh blew up');
    });
  });
});
