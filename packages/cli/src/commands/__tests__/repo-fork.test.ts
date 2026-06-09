import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// i18n stub
vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

// configService — capture addRepository payload to assert isolation
const mockGetRepository = vi.hoisted(() => vi.fn());
const mockAddRepository = vi.hoisted(() => vi.fn());
const mockAllocateNetworkId = vi.hoisted(() => vi.fn().mockResolvedValue(99999));
const mockRemoveRepository = vi.hoisted(() => vi.fn());
const mockGetLocalMachine = vi.hoisted(() =>
  vi.fn().mockResolvedValue({ ip: '127.0.0.1', user: 'root' })
);

vi.mock('../../services/config-resources.js', () => ({
  configService: {
    getRepository: mockGetRepository,
    addRepository: mockAddRepository,
    allocateNetworkId: mockAllocateNetworkId,
    removeRepository: mockRemoveRepository,
    getLocalMachine: mockGetLocalMachine,
  },
}));

// Renet executor — return success so handleForkAction reaches success path
const mockExecute = vi.hoisted(() =>
  vi.fn().mockResolvedValue({ success: true, allSteps: [], steps: [] })
);
const mockRefreshIdentityFor = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../../services/local-executor.js', () => ({
  localExecutorService: { execute: mockExecute, refreshIdentityFor: mockRefreshIdentityFor },
}));

// Machine connection pool — outer lease taken by handleForkAction
const mockLeaseRelease = vi.hoisted(() => vi.fn());
const mockAcquire = vi.hoisted(() => vi.fn());
vi.mock('../../services/machine-connection.js', () => ({
  machineConnections: { acquire: mockAcquire },
}));

// Repo-key deployment — no-op
vi.mock('../../services/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: vi.fn().mockResolvedValue(undefined),
}));

// Post-up tasks + early DNS — no-op
const mockPostRepoUpTasks = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const mockEnsureDns = vi.hoisted(() => vi.fn().mockResolvedValue('example.com'));
vi.mock('../repo-batch-utils.js', () => ({
  postRepoUpTasks: mockPostRepoUpTasks,
  ensureDns: mockEnsureDns,
}));

// SSH keypair — deterministic for assertion
vi.mock('../../utils/ssh-keygen.js', () => ({
  generateSSHKeyPair: () => ({ privateKey: 'mock-priv', publicKey: 'mock-pub' }),
}));

// Output / errors / local-execution-failure — silence
vi.mock('../../services/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    print: vi.fn(),
    setTimelineRendered: vi.fn(),
  },
}));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return {
    ...actual,
    handleError: (e: unknown) => {
      throw e;
    },
  };
});

const { handleForkAction } = await import('../repo-fork.js');

const PARENT = {
  repositoryGuid: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  tag: 'latest',
  credential: 'luks-pass',
  networkId: 100,
  sshPrivateKey: 'parent-ssh-priv',
  sshPublicKey: 'parent-ssh-pub',
  // The whole point of the test: parent has live secrets.
  secrets: {
    STRIPE_LIVE_KEY: { mode: 'env' as const, value: 'sk_live_REAL' },
    DKIM_PRIVATE: { mode: 'file' as const, value: '-----BEGIN KEY-----' },
  },
};

let stdoutSpy: ReturnType<typeof vi.spyOn>;

function stdoutText(): string {
  return stdoutSpy.mock.calls.map((c) => String(c[0])).join('');
}

beforeEach(() => {
  vi.clearAllMocks();
  // Parent lookup returns PARENT; fork-key lookup returns undefined (not yet registered)
  mockGetRepository.mockImplementation((ref: string) =>
    Promise.resolve(ref === 'app' ? PARENT : undefined)
  );
  mockExecute.mockResolvedValue({ success: true, allSteps: [], steps: [] });
  mockRefreshIdentityFor.mockResolvedValue(undefined);
  mockEnsureDns.mockResolvedValue('example.com');
  mockAcquire.mockResolvedValue({
    sftp: {},
    machine: { ip: '127.0.0.1', user: 'root' },
    sshPrivateKey: 'team-key',
    ensure: vi.fn().mockResolvedValue({}),
    release: mockLeaseRelease,
  });
  stdoutSpy = vi.spyOn(process.stdout, 'write').mockImplementation(() => true);
});

afterEach(() => {
  stdoutSpy.mockRestore();
  vi.clearAllMocks();
});

describe('repo fork — hard-isolate of secrets', () => {
  it('runtime: forking a parent with secrets produces a fork registration with NO secrets', async () => {
    await handleForkAction('app', 'staging', {
      machine: 'hostinger',
    });

    expect(mockAddRepository).toHaveBeenCalledOnce();
    const [forkKey, forkConfig] = mockAddRepository.mock.calls[0];
    expect(forkKey).toBe('app:staging');
    // The load-bearing assertion: secrets MUST NOT propagate
    expect(forkConfig.secrets).toBeUndefined();
    // Sanity: other fields propagate as the existing fork model expects
    expect(forkConfig.credential).toBe('luks-pass'); // shared (LUKS image is reflinked)
    expect(forkConfig.parentGuid).toBe(PARENT.repositoryGuid);
    expect(forkConfig.grandGuid).toBe(PARENT.repositoryGuid);
    // Fork mints fresh SSH keypair, never copies parent's
    expect(forkConfig.sshPrivateKey).toBe('mock-priv');
    expect(forkConfig.sshPrivateKey).not.toBe(PARENT.sshPrivateKey);
  });

  it('static: repo-fork.ts source must not reference parentConfig.secrets', () => {
    // Lightweight guard against future foot-guns. If someone adds
    // `secrets: parentConfig.secrets` to the addRepository call, this fires
    // and forces an explicit conversation about the threat model.
    const src = readFileSync(resolve(__dirname, '..', 'repo-fork.ts'), 'utf-8');
    expect(src).not.toMatch(/parentConfig\.secrets/);
  });

  it('rejects --tag latest before any config mutation (issue #495)', async () => {
    await expect(handleForkAction('app', 'latest', { machine: 'hostinger' })).rejects.toThrow(
      /tagReservedLatest|reserved/i
    );
    expect(mockAddRepository).not.toHaveBeenCalled();
    expect(mockRemoveRepository).not.toHaveBeenCalled();
    expect(mockExecute).not.toHaveBeenCalled();
  });
});

describe('repo fork — orchestration', () => {
  it('plain fork: defers identity refresh, no up leg, no post-up tasks, lease released', async () => {
    await handleForkAction('app', 'staging', { machine: 'hostinger' });

    expect(mockExecute).toHaveBeenCalledTimes(1);
    const call = mockExecute.mock.calls[0][0];
    expect(call.functionName).toBe('repository_fork');
    expect(call.deferIdentityRefresh).toBe(true);
    expect(call.params.up).toBeUndefined();
    expect(call.params.grand).toBeUndefined();
    expect(call.params.repo_name).toBeUndefined();

    expect(mockRefreshIdentityFor).toHaveBeenCalledExactlyOnceWith(
      'repository_fork',
      'hostinger',
      expect.objectContaining({ repository: 'app' })
    );
    expect(mockEnsureDns).not.toHaveBeenCalled();
    expect(mockPostRepoUpTasks).not.toHaveBeenCalled();
    expect(mockLeaseRelease).toHaveBeenCalledTimes(1);
  });

  it('compound --up: single execute with { up, grand, repo_name }, DNS fired early', async () => {
    mockExecute.mockResolvedValue({
      success: true,
      steps: [{ name: 'compose_up', duration_ms: 5 }],
      cliSteps: [{ name: 'ssh_connect', duration_ms: 3 }],
      allSteps: [],
    });

    await handleForkAction('app', 'staging', { machine: 'hostinger', up: true });

    // ONE compound execute — no chained repository_up leg
    expect(mockExecute).toHaveBeenCalledTimes(1);
    const call = mockExecute.mock.calls[0][0];
    expect(call.functionName).toBe('repository_fork');
    expect(call.params).toMatchObject({
      repository: 'app',
      network_id: 99999,
      up: true,
      grand: PARENT.repositoryGuid,
      repo_name: 'app:staging',
    });
    expect(call.deferIdentityRefresh).toBe(true);

    expect(mockEnsureDns).toHaveBeenCalledExactlyOnceWith('app:staging', 'hostinger');
    expect(mockRefreshIdentityFor).toHaveBeenCalledTimes(1);

    // postRepoUpTasks gets the pre-started dns promise + shared lease
    expect(mockPostRepoUpTasks).toHaveBeenCalledTimes(1);
    const [repoName, machineName, opts] = mockPostRepoUpTasks.mock.calls[0];
    expect(repoName).toBe('app:staging');
    expect(machineName).toBe('hostinger');
    expect(opts.dnsPromise).toBeInstanceOf(Promise);
    expect(opts.lease).toBeDefined();
    expect(mockLeaseRelease).toHaveBeenCalledTimes(1);
  });

  it('compound --up falls back to a chained up leg when the remote ignored --up', async () => {
    // Remote renet predates --up: fork succeeds but no up-phase steps appear
    mockExecute.mockResolvedValue({
      success: true,
      steps: [{ name: 'cow_clone', duration_ms: 7 }],
      allSteps: [],
    });

    await handleForkAction('app', 'staging', { machine: 'hostinger', up: true });

    expect(mockExecute).toHaveBeenCalledTimes(2);
    expect(mockExecute.mock.calls[0][0].functionName).toBe('repository_fork');
    const upCall = mockExecute.mock.calls[1][0];
    expect(upCall.functionName).toBe('repository_up');
    expect(upCall.params).toMatchObject({
      repository: 'app:staging',
      mount: true,
      grand: PARENT.repositoryGuid,
    });
    expect(mockPostRepoUpTasks).toHaveBeenCalledTimes(1);
  });

  it('compound --up retries as plain fork when the remote rejects the flag', async () => {
    mockExecute
      .mockResolvedValueOnce({
        success: false,
        exitCode: 1,
        error: 'unknown flag: --up',
        allSteps: [],
      })
      .mockResolvedValue({ success: true, steps: [], allSteps: [] });

    await handleForkAction('app', 'staging', { machine: 'hostinger', up: true });

    expect(mockExecute).toHaveBeenCalledTimes(3);
    const [first, second, third] = mockExecute.mock.calls.map((c) => c[0]);
    expect(first.functionName).toBe('repository_fork');
    expect(first.params.up).toBe(true);
    expect(second.functionName).toBe('repository_fork');
    expect(second.params.up).toBeUndefined();
    expect(third.functionName).toBe('repository_up');
    // No rollback: the retry succeeded
    expect(mockRemoveRepository).not.toHaveBeenCalled();
  });

  it('--checkpoint --up uses the legacy two-leg path (no compound params)', async () => {
    await handleForkAction('app', 'staging', {
      machine: 'hostinger',
      up: true,
      checkpoint: true,
    });

    expect(mockExecute).toHaveBeenCalledTimes(2);
    const forkCall = mockExecute.mock.calls[0][0];
    expect(forkCall.functionName).toBe('repository_fork');
    expect(forkCall.params.checkpoint).toBe(true);
    expect(forkCall.params.up).toBeUndefined();
    expect(mockExecute.mock.calls[1][0].functionName).toBe('repository_up');
  });

  it('fork failure rolls back the registration and releases the lease', async () => {
    mockExecute.mockResolvedValue({
      success: false,
      exitCode: 1,
      error: 'datastore full',
      allSteps: [],
    });

    await handleForkAction('app', 'staging', { machine: 'hostinger' });

    expect(mockRemoveRepository).toHaveBeenCalledWith('app:staging');
    expect(mockRefreshIdentityFor).not.toHaveBeenCalled();
    expect(mockPostRepoUpTasks).not.toHaveBeenCalled();
    expect(mockLeaseRelease).toHaveBeenCalledTimes(1);
  });
});

describe('repo fork — Total-at-end semantics', () => {
  it('prints Total exactly once, as the last line, after all phases settle', async () => {
    let releaseIdentity: () => void = () => {};
    mockRefreshIdentityFor.mockImplementation(
      () =>
        new Promise<void>((res) => {
          releaseIdentity = res;
        })
    );
    mockExecute.mockResolvedValue({
      success: true,
      steps: [{ name: 'compose_up', duration_ms: 5 }],
      cliSteps: [{ name: 'config', duration_ms: 2 }],
      allSteps: [],
    });

    const run = handleForkAction('app', 'staging', { machine: 'hostinger', up: true });
    // Let the orchestration reach the pending identity refresh
    await vi.waitFor(() => {
      expect(mockRefreshIdentityFor).toHaveBeenCalled();
    });
    expect(stdoutText()).not.toContain('Total:');

    releaseIdentity();
    await run;

    const out = stdoutText();
    const totals = out.match(/Total: /g) ?? [];
    expect(totals).toHaveLength(1);
    // Total is the very last thing written
    const lastWrite = String(stdoutSpy.mock.calls.at(-1)?.[0]);
    expect(lastWrite).toMatch(/^\nTotal: /);
    // Merged cliSteps from the fork result are rendered as step lines
    expect(out).toContain('Config loaded');
    // Parallel orchestrated phases carry the ∥ marker
    expect(out).toMatch(/License identity refreshed \(∥\)/);
    expect(out).toMatch(/DNS records ensured \(∥\)/);
  });

  it('plain fork failure path still ends with Total when steps were rendered', async () => {
    mockExecute.mockResolvedValue({
      success: false,
      exitCode: 1,
      error: 'boom',
      cliSteps: [{ name: 'ssh_connect', duration_ms: 4 }],
      allSteps: [],
    });

    await handleForkAction('app', 'staging', { machine: 'hostinger' });

    const lastWrite = String(stdoutSpy.mock.calls.at(-1)?.[0]);
    expect(lastWrite).toMatch(/^\nTotal: /);
  });
});
