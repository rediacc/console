import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  executeRepoFunction: vi.fn(),
  runCommandJob: vi.fn(),
  getRepository: vi.fn(),
  print: vi.fn(),
  isAgentEnvironment: vi.fn(),
  isRepoAllowedByGrandEnv: vi.fn(),
  isOverrideLegitimate: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));
vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return {
    ...actual,
    getOutputFormat: () => 'table',
    handleError: (error: unknown) => {
      throw error;
    },
  };
});
vi.mock('../_validate.js', () => ({ assertMachineExists: async () => undefined }));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: async (ref: string) => ({
    name: ref,
    repoKey: `${ref}:latest`,
    machineName: 'm1',
  }),
  resolveRepoTarget: async ({ machine }: { machine?: string }) => ({ machineName: machine }),
}));
vi.mock('../../utils/repo-executor.js', () => ({
  executeRepoFunction: mocks.executeRepoFunction,
  recordedDatastoreMount: async () => WK_DATASTORE_PATH,
}));
vi.mock('../../services/jobs/command-job.js', () => ({
  runCommandJob: mocks.runCommandJob,
  pendingExitCode: () => undefined,
}));
vi.mock('../../utils/agent-guard.js', () => ({ isAgentEnvironment: mocks.isAgentEnvironment }));
vi.mock('../../utils/grand-env.js', () => ({
  isRepoAllowedByGrandEnv: mocks.isRepoAllowedByGrandEnv,
}));
vi.mock('../../utils/process-ancestry.js', () => ({
  isOverrideLegitimate: mocks.isOverrideLegitimate,
}));
vi.mock('../../services/core/output.js', () => ({ outputService: { print: mocks.print } }));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getRepository: mocks.getRepository },
}));

const { registerRepoPolicyCommand, cpuMaxCores, limitRows, limitParamsOf } = await import(
  '../repo-policy.js'
);

async function run(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerRepoPolicyCommand(program.command('repo'));
  await program.parseAsync(['repo', 'policy', ...argv], { from: 'user' });
}

const GRANT_STDOUT = JSON.stringify({
  version: 1,
  repo_mount_path: `${WK_DATASTORE_PATH}/mounts/g-app`,
  limits: {
    memory_max: 1610612736,
    cpu_max: '250000 100000',
    io_max: { rbps: 209715200 },
    pids_max: 4096,
  },
  ram_volume: { size: 268435456 },
});

function limitCalls(): unknown[][] {
  return mocks.executeRepoFunction.mock.calls.filter((c) =>
    String(c[0]).startsWith('repository_limits_')
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.isAgentEnvironment.mockReturnValue(false);
  mocks.isRepoAllowedByGrandEnv.mockReturnValue(false);
  mocks.isOverrideLegitimate.mockReturnValue(false);
  // A grand repository: no grandGuid of its own to differ from.
  mocks.getRepository.mockResolvedValue({ repositoryGuid: 'g-app' });
  mocks.executeRepoFunction.mockResolvedValue({ success: true, stdout: GRANT_STDOUT });
  mocks.runCommandJob.mockResolvedValue({ kind: 'finished', result: { success: true } });
});

describe('rdc repo policy set limit flags (PLAN-repo-resource-limits R5)', () => {
  it('accepts --memory-max and routes it to repository_limits_set, not the size policy', async () => {
    await run(['set', 'x', '--memory-max', '1G']);
    expect(limitCalls()).toHaveLength(1);
    const [fn, repoKey, machine, params, opts] = limitCalls()[0] as [
      string,
      string,
      string,
      Record<string, unknown>,
      { job: { verb: string; steps: { name: string }[] } },
    ];
    expect([fn, repoKey, machine]).toEqual(['repository_limits_set', 'x:latest', 'm1']);
    expect(params).toEqual({ memory_max: '1G' });
    expect(opts.job.verb).toBe('repo policy set');
    expect(opts.job.steps.map((s) => s.name)).toEqual(['renderLimitsResult']);
    expect(mocks.runCommandJob).not.toHaveBeenCalled();
  });

  it('sends every limit flag, and --force only alongside one', async () => {
    await run([
      'set',
      'x',
      '--memory-max',
      '10G',
      '--memory-high',
      '8G',
      '--cpu-max',
      '2.5',
      '--io-max',
      'rbps=200M,wbps=100M',
      '--pids-max',
      '4096',
      '--ram-volume',
      '8G',
      '--force',
    ]);
    expect(limitCalls()[0][3]).toEqual({
      memory_max: '10G',
      memory_high: '8G',
      cpu_max: '2.5',
      io_max: 'rbps=200M,wbps=100M',
      pids_max: '4096',
      ram_volume: '8G',
      force: true,
    });
    expect(limitParamsOf({ force: true })).toEqual({});
    expect(limitParamsOf({ clearLimits: true })).toEqual({ clear_limits: true });
  });

  it('runs both functions when size and limit flags are mixed', async () => {
    await run(['set', 'x', '--max-quota', '200G', '--clear-limits']);
    expect(mocks.runCommandJob).toHaveBeenCalledTimes(1);
    expect(mocks.runCommandJob.mock.calls[0][1].functionName).toBe('repository_policy_set');
    expect(limitCalls()[0][3]).toEqual({ clear_limits: true });
  });

  it('keeps the size-only form on repository_policy_set alone', async () => {
    await run(['set', 'x', '--auto-trim', 'true', '--force']);
    expect(mocks.runCommandJob).toHaveBeenCalledTimes(1);
    expect(limitCalls()).toHaveLength(0);
  });

  it('refuses a limit flag without a ref', async () => {
    await expect(run(['set', '-m', 'm1', '--memory-max', '1G'])).rejects.toThrow(
      'commands.repo.policy.limitsNeedRef'
    );
    expect(mocks.executeRepoFunction).not.toHaveBeenCalled();
    expect(mocks.runCommandJob).not.toHaveBeenCalled();
  });

  it('refuses an agent a limit change on a grand repository without the operator override', async () => {
    mocks.isAgentEnvironment.mockReturnValue(true);
    await expect(run(['set', 'x', '--memory-max', '1G'])).rejects.toThrow(
      'errors.agent.limitsGrantBlocked'
    );
    mocks.isRepoAllowedByGrandEnv.mockReturnValue(true);
    await expect(run(['set', 'x', '--memory-max', '1G'])).rejects.toThrow(
      'errors.agent.limitsGrantOverride'
    );
    expect(limitCalls()).toHaveLength(0);
    mocks.isOverrideLegitimate.mockReturnValue(true);
    await run(['set', 'x', '--memory-max', '1G']);
    expect(limitCalls()).toHaveLength(1);
  });

  it('lets an agent change a fork freely', async () => {
    mocks.isAgentEnvironment.mockReturnValue(true);
    mocks.getRepository.mockResolvedValue({ repositoryGuid: 'g-fork', grandGuid: 'g-app' });
    await run(['set', 'x', '--memory-max', '1G']);
    expect(limitCalls()).toHaveLength(1);
  });
});

describe('rdc repo policy get <ref> adds the limits table', () => {
  it('runs repository_limits_show after the size policy for a ref, and not machine-wide', async () => {
    await run(['get', 'x']);
    expect(mocks.runCommandJob.mock.calls[0][1].functionName).toBe('repository_policy_get');
    expect(limitCalls().map((c) => c[0])).toEqual(['repository_limits_show']);

    vi.clearAllMocks();
    mocks.runCommandJob.mockResolvedValue({ kind: 'finished', result: { success: true } });
    await run(['get', '-m', 'm1']);
    expect(limitCalls()).toHaveLength(0);
  });

  it('renders the grant limits as rows, a missing limit as -', async () => {
    expect(cpuMaxCores('250000 100000')).toBe('2.5 cores');
    expect(cpuMaxCores('400000 100000')).toBe('4 cores');
    expect(cpuMaxCores('odd')).toBe('odd');
    const rows = await limitRows(JSON.parse(GRANT_STDOUT));
    expect(rows).toEqual([
      { limit: 'Memory max', value: '1.5G' },
      { limit: 'Memory high', value: '-' },
      { limit: 'CPU max', value: '2.5 cores' },
      { limit: 'I/O max', value: 'rbps=200M' },
      { limit: 'Pids max', value: '4096' },
      { limit: 'RAM volume', value: '256M' },
    ]);
    expect((await limitRows({})).every((r) => r.value === '-')).toBe(true);
  });
});
