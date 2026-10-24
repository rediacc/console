/**
 * The CLI half of the runtime converge (agent/plans/PLAN-renet-runtime-converge.md, C1).
 *
 * Every remote effect goes through injected deps, so these drive the decision
 * logic directly: when a pass runs, what its vault carries, and that the router
 * refresh comes after it.
 */

import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RepositoryConfig } from '../../../types/index.js';

const { mockListRepositories, mockInfo, mockWarn } = vi.hoisted(() => ({
  mockListRepositories: vi.fn(),
  mockInfo: vi.fn(),
  mockWarn: vi.fn(),
}));

vi.mock('../../config/config-resources.js', () => ({
  configService: { listRepositories: mockListRepositories },
}));
vi.mock('../../core/output.js', () => ({
  outputService: { info: mockInfo, warn: mockWarn, success: vi.fn() },
}));

const {
  CONVERGE_FUNCTION,
  SKIP_RUNTIME_CONVERGE_ENV,
  buildConvergeParams,
  buildRuntimeStatusCommand,
  collectEnvSecretsByGuid,
  convergeIfStale,
  injectConvergeEnvSecrets,
  parseConvergeReport,
  routerRefreshAfterPass,
  shouldCheckRuntimeAfterUpload,
} = await import('../runtime-converge.js');
type AutoConvergeDeps = import('../runtime-converge.js').AutoConvergeDeps;

const GUID_A = 'aaaaaaaa-0000-4000-8000-000000000001';
const GUID_B = 'bbbbbbbb-0000-4000-8000-000000000002';
const GUID_ELSEWHERE = 'cccccccc-0000-4000-8000-000000000003';

function repo(guid: string, secrets: RepositoryConfig['secrets']): { config: RepositoryConfig } {
  return { config: { repositoryGuid: guid, secrets } as RepositoryConfig };
}

const REPOS = [
  repo(GUID_A, {
    DB_PASS: { mode: 'env', value: 'a-db' },
    TLS_KEY: { mode: 'file', value: 'a-tls' },
  }),
  repo(GUID_B, { API_TOKEN: { mode: 'env', value: 'b-token' } }),
  repo(GUID_ELSEWHERE, { OTHER: { mode: 'env', value: 'elsewhere' } }),
];

/** The vault the executor's buildLocalVault would produce for the converge function. */
function baseVault(params: Record<string, unknown>): string {
  return JSON.stringify({
    task: { function: CONVERGE_FUNCTION },
    params,
    repository_credentials: { [GUID_A]: 'pw-a', [GUID_B]: 'pw-b' },
    repositories: {
      'app-a': { guid: GUID_A, name: 'app-a', network_id: 2816 },
      'app-a:latest': { guid: GUID_A, name: 'app-a:latest', network_id: 2816 },
      'app-b': {
        guid: GUID_B,
        name: 'app-b',
        network_id: 2880,
        secret_files: [{ name: 'X', value: 'x' }],
      },
      'app-c': { guid: GUID_ELSEWHERE, name: 'app-c', network_id: 2944 },
    },
  });
}

function statusJson(stale: number, guids: string[] = [GUID_A, GUID_B]): string {
  return JSON.stringify({
    runtime_epoch: 1,
    renet_sha256: 'f'.repeat(64),
    policy: 'epoch',
    stale,
    pending: false,
    repos: guids.map((guid, i) => ({
      guid,
      state: i < stale ? 'stale' : 'current',
      reasons: i < stale ? ['no_stamp'] : [],
      network_id: 2816 + i * 64,
    })),
  });
}

function reportJson(summary: Partial<Record<string, number>>, dryRun = false): string {
  return `[machine_converge_runtime] ${JSON.stringify({
    policy: 'epoch',
    runtime_epoch: 1,
    dry_run: dryRun,
    aborted: false,
    plan: [{ guid: GUID_A, action: 'converged', stale_reasons: ['no_stamp'] }],
    results: [{ guid: GUID_A, status: 'converged', network_id: 2816 }],
    summary: {
      total: 1,
      converged: 0,
      would_converge: 0,
      skipped: 0,
      failed: 0,
      pending: 0,
      ...summary,
    },
  })}`;
}

/** Fake deps that log every remote effect in order. */
function fakeDeps(opts: { status?: string | Error; runStdout?: string; runSuccess?: boolean }) {
  const calls: string[] = [];
  const vaults: string[] = [];
  const deps: AutoConvergeDeps = {
    sftp: {
      exec: vi.fn((cmd: string) => {
        calls.push(`exec:${cmd.includes('runtime status') ? 'status' : cmd}`);
        if (opts.status instanceof Error) return Promise.reject(opts.status);
        return Promise.resolve(opts.status ?? statusJson(0));
      }),
    },
    remoteRenetPath: '/usr/lib/rediacc/renet/1.2.3/renet',
    machineName: 'hostinger',
    datastore: WK_DATASTORE_PATH,
    buildBaseVault: (params) => baseVault(params),
    run: vi.fn((vault: string) => {
      calls.push('run');
      vaults.push(vault);
      return Promise.resolve({
        success: opts.runSuccess ?? true,
        stdout: opts.runStdout ?? reportJson({ converged: 1 }),
      });
    }),
    refreshRouter: vi.fn(() => {
      calls.push('router');
      return Promise.resolve(true);
    }),
  };
  return { deps, calls, vaults };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockListRepositories.mockResolvedValue(REPOS.map((r, i) => ({ name: `r${i}`, ...r })));
  delete process.env.REDIACC_SKIP_ROUTER_RESTART;
});

describe('shouldCheckRuntimeAfterUpload', () => {
  it('checks after an upload', () => {
    expect(shouldCheckRuntimeAfterUpload('repository_up', true, {})).toBe(true);
  });

  it('does not check when the binary was only verified', () => {
    expect(shouldCheckRuntimeAfterUpload('repository_up', false, {})).toBe(false);
  });

  it(`honours ${SKIP_RUNTIME_CONVERGE_ENV}=1`, () => {
    expect(
      shouldCheckRuntimeAfterUpload('repository_up', true, { [SKIP_RUNTIME_CONVERGE_ENV]: '1' })
    ).toBe(false);
  });

  it('never triggers the converge from the converge itself', () => {
    expect(shouldCheckRuntimeAfterUpload(CONVERGE_FUNCTION, true, {})).toBe(false);
  });
});

describe('buildRuntimeStatusCommand', () => {
  it('reads the status as JSON for the machine datastore', () => {
    expect(buildRuntimeStatusCommand('/usr/bin/renet', WK_DATASTORE_PATH, 'always')).toBe(
      `sudo '/usr/bin/renet' runtime status --json --datastore '${WK_DATASTORE_PATH}' --policy 'always'`
    );
  });
});

describe('the converge vault', () => {
  it("gives each repository its own env secrets and no other repository's", () => {
    const env = collectEnvSecretsByGuid(REPOS);
    expect(env.get(GUID_A)).toEqual({ REDIACC_SECRET_DB_PASS: 'a-db' });

    const vault = JSON.parse(
      injectConvergeEnvSecrets(baseVault({}), env, new Set([GUID_A, GUID_B]))
    ) as { repositories: Record<string, { env_secrets?: Record<string, string> }> };

    expect(vault.repositories['app-a'].env_secrets).toEqual({ REDIACC_SECRET_DB_PASS: 'a-db' });
    expect(vault.repositories['app-a:latest'].env_secrets).toEqual({
      REDIACC_SECRET_DB_PASS: 'a-db',
    });
    expect(vault.repositories['app-b'].env_secrets).toEqual({
      REDIACC_SECRET_API_TOKEN: 'b-token',
    });
  });

  it('never ships the env secrets of a repository the machine does not hold', () => {
    const vault = injectConvergeEnvSecrets(
      baseVault({}),
      collectEnvSecretsByGuid(REPOS),
      new Set([GUID_A, GUID_B])
    );
    expect(vault).not.toContain('elsewhere');
    expect(vault).not.toContain('REDIACC_SECRET_OTHER');
  });

  it('keeps file secrets out of env_secrets', () => {
    expect(collectEnvSecretsByGuid(REPOS).get(GUID_A)).not.toHaveProperty('REDIACC_SECRET_TLS_KEY');
  });
});

describe('buildConvergeParams', () => {
  it('maps every flag onto the bridge function params', () => {
    expect(
      buildConvergeParams({
        dryRun: true,
        policy: 'always',
        includeUnknown: true,
        continueOnError: true,
      })
    ).toEqual({ dry_run: true, policy: 'always', include_unknown: true, continue_on_error: true });
    expect(buildConvergeParams({})).toEqual({});
  });
});

describe('parseConvergeReport', () => {
  it('reads the relayed JSON report', () => {
    expect(parseConvergeReport(reportJson({ converged: 1 }))?.summary.converged).toBe(1);
  });

  it('is null without a report', () => {
    expect(parseConvergeReport('Error: boom')).toBeNull();
    expect(parseConvergeReport(undefined)).toBeNull();
  });
});

describe('routerRefreshAfterPass', () => {
  const summary = (s: Partial<Record<string, number>>) => ({
    total: 1,
    converged: 0,
    would_converge: 0,
    skipped: 0,
    failed: 0,
    pending: 0,
    ...s,
  });

  it('repays the owed refresh when no pass ran', () => {
    expect(routerRefreshAfterPass({ due: true, env: {} })).toBe(true);
    expect(routerRefreshAfterPass({ due: false, env: {} })).toBe(false);
  });

  it('refreshes after a real pass that moved a repo, owed or not', () => {
    expect(
      routerRefreshAfterPass({ due: false, summary: summary({ converged: 1 }), env: {} })
    ).toBe(true);
  });

  it('does not refresh on a dry run that would move a repo', () => {
    expect(
      routerRefreshAfterPass({
        due: true,
        dryRun: true,
        summary: summary({ would_converge: 2 }),
        env: {},
      })
    ).toBe(false);
  });

  it('respects the router opt-outs', () => {
    expect(routerRefreshAfterPass({ due: true, skipRouterRestart: true, env: {} })).toBe(false);
    expect(routerRefreshAfterPass({ due: true, env: { REDIACC_SKIP_ROUTER_RESTART: '1' } })).toBe(
      false
    );
  });
});

describe('convergeIfStale', () => {
  it('runs the pass when a repo is stale, then refreshes the router', async () => {
    const { deps, calls, vaults } = fakeDeps({ status: statusJson(1) });

    const outcome = await convergeIfStale(deps, { checkRuntime: true, routerRefreshDue: true });

    expect(outcome.converged).toBe(true);
    expect(calls).toEqual(['exec:status', 'run', 'router']);
    const vault = JSON.parse(vaults[0]) as {
      task: { function: string };
      repositories: Record<string, { env_secrets?: unknown }>;
    };
    expect(vault.task.function).toBe(CONVERGE_FUNCTION);
    expect(vault.repositories['app-b'].env_secrets).toEqual({
      REDIACC_SECRET_API_TOKEN: 'b-token',
    });
    expect(vault.repositories['app-c'].env_secrets).toBeUndefined();
  });

  it('does not run a pass when nothing is stale, and still repays the owed refresh', async () => {
    const { deps, calls } = fakeDeps({ status: statusJson(0) });

    const outcome = await convergeIfStale(deps, { checkRuntime: true, routerRefreshDue: true });

    expect(outcome.converged).toBe(false);
    expect(calls).toEqual(['exec:status', 'router']);
  });

  it('reads nothing when the runtime check is off', async () => {
    const { deps, calls } = fakeDeps({ status: statusJson(3) });

    await convergeIfStale(deps, { checkRuntime: false, routerRefreshDue: false });

    expect(calls).toEqual([]);
  });

  it('warns and runs no pass when the status cannot be read', async () => {
    const { deps, calls } = fakeDeps({ status: new Error('unknown command "runtime"') });

    const outcome = await convergeIfStale(deps, { checkRuntime: true, routerRefreshDue: true });

    expect(outcome.converged).toBe(false);
    expect(calls).toEqual(['exec:status', 'router']);
    expect(mockWarn).toHaveBeenCalledTimes(1);
  });

  it('warns with the resume command when the pass fails without a report', async () => {
    const { deps } = fakeDeps({ status: statusJson(1), runSuccess: false, runStdout: '' });

    await convergeIfStale(deps, { checkRuntime: true, routerRefreshDue: false });

    expect(mockWarn).toHaveBeenCalledTimes(1);
  });
});
