import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  runCommandJob: vi.fn(),
  getRepository: vi.fn(),
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
  executeRepoFunction: vi.fn(),
  recordedDatastoreMount: async () => WK_DATASTORE_PATH,
}));
vi.mock('../../services/jobs/command-job.js', () => ({
  runCommandJob: mocks.runCommandJob,
  pendingExitCode: () => undefined,
}));
vi.mock('../../services/core/output.js', () => ({ outputService: { print: vi.fn() } }));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getRepository: mocks.getRepository },
}));

const { registerRepoPolicyCommand } = await import('../repo-policy.js');

async function run(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerRepoPolicyCommand(program.command('repo'));
  await program.parseAsync(['repo', 'policy', ...argv], { from: 'user' });
}

function policySetParams(): Record<string, unknown> {
  const call = mocks.runCommandJob.mock.calls.find(
    (c) => (c[1] as { functionName: string }).functionName === 'repository_policy_set'
  );
  return (call?.[1] as { params: Record<string, unknown> }).params;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getRepository.mockResolvedValue({ repositoryGuid: 'g-app' });
  mocks.runCommandJob.mockResolvedValue({ kind: 'finished', result: { success: true } });
});

describe('rdc repo policy set --grow-when-free-bytes', () => {
  it('passes the size through as grow_when_free_bytes', async () => {
    await run(['set', 'x', '--grow-when-free-bytes', '1G']);
    expect(policySetParams()).toEqual({ name: 'g-app', grow_when_free_bytes: '1G' });
  });

  it('passes 0 (one grow step) through, and omits the param when the flag is absent', async () => {
    await run(['set', 'x', '--grow-when-free-bytes', '0']);
    expect(policySetParams().grow_when_free_bytes).toBe('0');

    mocks.runCommandJob.mockClear();
    await run(['set', 'x', '--max-quota', '200G']);
    expect(policySetParams()).toEqual({ name: 'g-app', max_quota: '200G' });
  });

  it('runs the size policy function when it is the only flag given', async () => {
    await run(['set', 'x', '--grow-when-free-bytes', '2G']);
    expect(mocks.runCommandJob).toHaveBeenCalledTimes(1);
  });
});
