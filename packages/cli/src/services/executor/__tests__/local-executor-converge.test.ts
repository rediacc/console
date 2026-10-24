/**
 * The executor's runtime converge trigger (agent/plans/PLAN-renet-runtime-converge.md, D5,
 * decision 2): after a renet upload, a stale runtime is converged before the requested
 * function, the router refresh comes after that pass, and the converge never triggers itself.
 *
 * The SSH session is a fake whose exec/execStreaming log every remote command in order.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

type BuildLocalVaultOptions = Parameters<
  typeof import('../../renet/renet-execution.js').buildLocalVault
>[0];

const { calls, state, mockExec, mockExecStreaming, mockAcquireRemoteRenet } = vi.hoisted(() => {
  const calls: string[] = [];
  const state = {
    status: '',
    convergeStdout: '',
    stdins: [] as string[],
  };
  return {
    calls,
    state,
    mockExec: vi.fn((cmd: string) => {
      if (cmd.includes('runtime status')) {
        calls.push('status');
        return Promise.resolve(state.status);
      }
      if (cmd.includes('rediacc-router')) {
        calls.push('router');
        return Promise.resolve('RESTARTED\n');
      }
      calls.push(`exec:${cmd}`);
      return Promise.resolve('');
    }),
    mockExecStreaming: vi.fn(
      (_cmd: string, opts: { stdin?: string; onStdout?: (d: string) => void }) => {
        const stdin = opts.stdin ?? '';
        state.stdins.push(stdin);
        const fn = /"function":"([a-z_]+)"/.exec(stdin)?.[1] ?? 'unknown';
        calls.push(`run:${fn}`);
        if (fn === 'machine_converge_runtime') opts.onStdout?.(state.convergeStdout);
        return Promise.resolve(0);
      }
    ),
    mockAcquireRemoteRenet: vi.fn(),
  };
});

const GUID_A = 'aaaaaaaa-0000-4000-8000-000000000001';
const GUID_B = 'bbbbbbbb-0000-4000-8000-000000000002';

vi.mock('../../machine/machine-connection.js', () => ({
  machineConnections: {
    acquireFor: vi.fn(() =>
      Promise.resolve({
        sftp: { exec: mockExec, execStreaming: mockExecStreaming },
        release: vi.fn(),
      })
    ),
  },
  withSharedOrPooledSftp: vi.fn(),
}));

vi.mock('../../config/config-resources.js', () => ({
  configService: {
    getLocalConfig: vi.fn(() =>
      Promise.resolve({
        sshPrivateKey: 'PRIVATE_KEY',
        sshPublicKey: 'PUBLIC_KEY',
        ssh: { privateKeyPath: '/tmp/id', publicKeyPath: '/tmp/id.pub' },
      })
    ),
    getLocalMachine: vi.fn(() =>
      Promise.resolve({ ip: '127.0.0.1', user: 'root', port: 22, knownHosts: 'kh' })
    ),
    getRepository: vi.fn(() => Promise.resolve(undefined)),
    getRepositoryKey: vi.fn(() => Promise.resolve(undefined)),
    listStorages: vi.fn(() => Promise.resolve([])),
    listRepositories: vi.fn(() =>
      Promise.resolve([
        {
          name: 'app-a',
          config: {
            repositoryGuid: GUID_A,
            networkId: 2816,
            secrets: { DB_PASS: { mode: 'env', value: 'a-db' } },
          },
        },
        {
          name: 'app-b',
          config: {
            repositoryGuid: GUID_B,
            networkId: 2880,
            secrets: { API_TOKEN: { mode: 'env', value: 'b-token' } },
          },
        },
      ])
    ),
  },
}));

vi.mock('../../renet/renet-execution.js', () => ({
  // A vault shaped like the real one where the converge reads it: task, params, repositories.
  buildLocalVault: vi.fn((opts: BuildLocalVaultOptions) =>
    JSON.stringify({
      task: { function: opts.functionName },
      params: opts.params,
      repositories: Object.fromEntries(
        Object.entries(opts.repositoryConfigs ?? {}).map(([name, c]) => [
          name,
          { guid: c.guid, name, network_id: c.networkId },
        ])
      ),
    })
  ),
  acquireRemoteRenet: mockAcquireRemoteRenet,
  readSSHKey: vi.fn(() => 'PRIVATE_KEY'),
  readOptionalSSHKey: vi.fn(() => 'PUBLIC_KEY'),
  verifyMachineSetup: vi.fn(),
}));

vi.mock('../license-recovery.js', () => ({
  ensureRepoLicenseForProvisioning: vi.fn(),
  ensureRepoLicenseForRestore: vi.fn(),
  maybeRefreshRepoIdentity: vi.fn(),
  maybeRefreshRepoLicenses: vi.fn(),
  needsLicenseRecovery: vi.fn(() => false),
  refreshRepoIdentityFor: vi.fn(),
  resolveLicenseFailure: vi.fn(),
}));
vi.mock('../../telemetry/telemetry.js', () => ({ isTelemetryDisabled: () => true }));
vi.mock('../../telemetry/otlp-credentials.js', () => ({ fetchOtlpCredentials: vi.fn() }));
vi.mock('../../core/audit.js', () => ({ auditService: { recordOperation: vi.fn() } }));

const { localExecutorService } = await import('../local-executor.js');

function statusJson(stale: number): string {
  return JSON.stringify({
    runtime_epoch: 1,
    policy: 'epoch',
    stale,
    pending: false,
    repos: [
      { guid: GUID_A, state: stale > 0 ? 'stale' : 'current', reasons: [], network_id: 2816 },
    ],
  });
}

function reportJson(summary: Record<string, number>): string {
  return `[machine_converge_runtime] ${JSON.stringify({
    policy: 'epoch',
    runtime_epoch: 1,
    dry_run: false,
    aborted: false,
    plan: [],
    results: [],
    summary: {
      total: 1,
      converged: 0,
      would_converge: 0,
      skipped: 0,
      failed: 0,
      pending: 0,
      ...summary,
    },
  })}\n`;
}

function provisioned(uploaded: boolean, routerRefreshDue = uploaded) {
  mockAcquireRemoteRenet.mockResolvedValue({
    remotePath: '/usr/lib/rediacc/renet/1.2.3/renet',
    uploaded,
    drift: null,
    routerRefreshDue,
  });
}

function run(functionName: string, params: Record<string, unknown> = {}) {
  return localExecutorService.execute({
    functionName,
    machineName: 'hostinger',
    params,
    captureOutput: true,
    quietSpinners: true,
  });
}

/** The vault the run of `fn` received on stdin. */
function vaultOf(fn: string): {
  params: Record<string, unknown>;
  repositories: Record<string, { env_secrets?: Record<string, string> }>;
} {
  const raw = state.stdins.find((s) => s.includes(`"function":"${fn}"`));
  if (!raw) throw new Error(`no run of ${fn}`);
  return JSON.parse(raw.slice(raw.indexOf('{"task"'))) as ReturnType<typeof vaultOf>;
}

beforeEach(() => {
  vi.clearAllMocks();
  calls.length = 0;
  state.stdins.length = 0;
  state.status = statusJson(1);
  state.convergeStdout = reportJson({ converged: 1 });
  delete process.env.REDIACC_SKIP_RUNTIME_CONVERGE;
  delete process.env.REDIACC_SKIP_ROUTER_RESTART;
});

describe('the runtime converge trigger', () => {
  it('defers the router refresh at provisioning', async () => {
    provisioned(false);
    await run('repository_up', { repository: 'app-a' });
    expect(mockAcquireRemoteRenet.mock.calls[0][4]).toMatchObject({ deferRouterRefresh: true });
  });

  it('converges a stale runtime after an upload, then refreshes the router, then runs the function', async () => {
    provisioned(true);

    const result = await run('repository_up', { repository: 'app-a' });

    expect(result.success).toBe(true);
    expect(calls).toEqual([
      'status',
      'run:machine_converge_runtime',
      'router',
      'run:repository_up',
    ]);
  });

  it('does not read the runtime when the binary was only verified', async () => {
    provisioned(false);

    await run('repository_up', { repository: 'app-a' });

    expect(calls).toEqual(['run:repository_up']);
  });

  it('skips the pass under REDIACC_SKIP_RUNTIME_CONVERGE=1 but still repays the router refresh', async () => {
    provisioned(true);
    process.env.REDIACC_SKIP_RUNTIME_CONVERGE = '1';

    await run('repository_up', { repository: 'app-a' });

    expect(calls).toEqual(['router', 'run:repository_up']);
  });

  it('refreshes the router without a pass when nothing is stale', async () => {
    provisioned(true);
    state.status = statusJson(0);

    await run('repository_up', { repository: 'app-a' });

    expect(calls).toEqual(['status', 'router', 'run:repository_up']);
  });

  it('never triggers a second converge from the converge itself', async () => {
    provisioned(true);

    await run('machine_converge_runtime');

    expect(calls.filter((c) => c === 'run:machine_converge_runtime')).toHaveLength(1);
    // The status read only scopes the vault; the router refresh follows the pass.
    expect(calls).toEqual(['status', 'run:machine_converge_runtime', 'router']);
  });

  it("carries each repo's own env secrets in the converge vault, and only for repos the machine holds", async () => {
    provisioned(true);

    await run('repository_up', { repository: 'app-a' });

    const vault = vaultOf('machine_converge_runtime');
    expect(vault.repositories['app-a'].env_secrets).toEqual({ REDIACC_SECRET_DB_PASS: 'a-db' });
    // app-b is not in the machine's status, so its secrets never leave the CLI.
    expect(vault.repositories['app-b'].env_secrets).toBeUndefined();
    // The requested function's own vault carries no env_secrets map at all.
    expect(JSON.stringify(vaultOf('repository_up'))).not.toContain('env_secrets');
  });

  it('passes dry_run through and refreshes nothing on a dry run that would move a repo', async () => {
    provisioned(false);
    state.convergeStdout = reportJson({ would_converge: 1 });

    await run('machine_converge_runtime', { dry_run: true });

    expect(vaultOf('machine_converge_runtime').params).toEqual({ dry_run: true });
    expect(calls).toEqual(['status', 'run:machine_converge_runtime']);
  });

  it('plans a dry run with the remote renet as it is: read-only access, never a provision', async () => {
    provisioned(false);
    state.convergeStdout = reportJson({ would_converge: 1 });

    await run('machine_converge_runtime', { dry_run: true });

    expect(mockAcquireRemoteRenet.mock.calls[0][0]).toBe('read-only');
  });

  it('still provisions for a real converge', async () => {
    provisioned(true);

    await run('machine_converge_runtime', {});
    await run('machine_converge_runtime', { dry_run: false });

    expect(mockAcquireRemoteRenet.mock.calls.map((c) => c[0])).toEqual(['provision', 'provision']);
  });

  it('tells the operator to run the real setup or converge when the remote renet is too old to plan a dry run', async () => {
    provisioned(false);
    mockExec.mockImplementationOnce(() =>
      Promise.reject(new Error('Error: unknown command "runtime" for "renet"'))
    );

    const outcome = await run('machine_converge_runtime', { dry_run: true }).then(
      (r) => r.error ?? '',
      (e: unknown) => (e instanceof Error ? e.message : String(e))
    );

    expect(outcome).toContain('rdc machine setup hostinger');
    expect(outcome).toContain('machine converge hostinger');
    expect(calls).not.toContain('run:machine_converge_runtime');
  });

  it('keeps an SSH failure during a dry-run status read as its own error, not a too-old renet', async () => {
    provisioned(false);
    mockExec.mockImplementationOnce(() => Promise.reject(new Error('SSH connection timed out')));

    const outcome = await run('machine_converge_runtime', { dry_run: true }).then(
      (r) => r.error ?? '',
      (e: unknown) => (e instanceof Error ? e.message : String(e))
    );

    expect(outcome).toContain('SSH connection timed out');
    expect(outcome).not.toContain('rdc machine setup hostinger');
    expect(calls).not.toContain('run:machine_converge_runtime');
  });

  it('keeps an error that only echoes the word status as its own error', async () => {
    provisioned(false);
    mockExec.mockImplementationOnce(() =>
      Promise.reject(new Error('sftp: unknown command status 255 from the remote shell'))
    );

    const outcome = await run('machine_converge_runtime', { dry_run: true }).then(
      (r) => r.error ?? '',
      (e: unknown) => (e instanceof Error ? e.message : String(e))
    );

    expect(outcome).toContain('sftp: unknown command status 255 from the remote shell');
    expect(outcome).not.toContain('rdc machine setup hostinger');
  });
  it('keeps going with the requested function when the converge pass fails', async () => {
    provisioned(true);
    mockExecStreaming.mockImplementationOnce((_cmd: string, opts: { stdin?: string }) => {
      state.stdins.push(opts.stdin ?? '');
      calls.push('run:machine_converge_runtime');
      return Promise.resolve(1);
    });

    const result = await run('repository_up', { repository: 'app-a' });

    expect(result.success).toBe(true);
    expect(calls).toEqual([
      'status',
      'run:machine_converge_runtime',
      'router',
      'run:repository_up',
    ]);
  });
});
