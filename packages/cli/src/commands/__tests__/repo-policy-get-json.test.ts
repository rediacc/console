/**
 * `repo policy get <ref> -o json|yaml` runs two jobs (the size policy, then the limits)
 * and must still print exactly ONE document on stdout.
 */
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlannedStep } from '../../services/jobs/steps-support.js';

const mocks = vi.hoisted(() => ({
  format: 'json' as 'json' | 'yaml' | 'table',
  executeRepoFunction: vi.fn(),
  runCommandJob: vi.fn(),
  print: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));
vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return {
    ...actual,
    getOutputFormat: () => mocks.format,
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
  recordedDatastoreMount: async () => '/mnt/rediacc',
}));
vi.mock('../../services/jobs/command-job.js', () => ({
  runCommandJob: mocks.runCommandJob,
  pendingExitCode: () => 1,
}));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { print: mocks.print, info: vi.fn(), warn: vi.fn() },
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getRepository: async () => ({ repositoryGuid: 'g-app' }) },
}));

const { registerRepoPolicyCommand } = await import('../repo-policy.js');
const { resolveStepHandler } = await import('../../services/jobs/steps.js');

const POLICY_STDOUT = JSON.stringify({ effective: { auto_grow: true }, repo_override: null });
const LIMITS_STDOUT = JSON.stringify({ limits: { pids_max: 4096 }, ram_volume: { size: 1 } });

type Planned = Pick<PlannedStep, 'name' | 'params'>;

/** Settle planned steps the way the job does once its function finished. */
async function settle(steps: Planned[], output: string): Promise<void> {
  for (const step of steps) {
    const handler = await resolveStepHandler(step.name);
    await handler({
      jobId: 'j1',
      machine: 'm1',
      params: step.params,
      state: 'succeeded',
      output,
      exitCode: 0,
    });
  }
}

async function run(): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerRepoPolicyCommand(program.command('repo'));
  await program.parseAsync(['repo', 'policy', 'get', 'x'], { from: 'user' });
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.format = 'json';
  mocks.runCommandJob.mockImplementation(
    async (_verb: string, _options: unknown, steps: Planned[]) => {
      await settle(steps, POLICY_STDOUT);
      return { kind: 'finished', result: { success: true } };
    }
  );
  mocks.executeRepoFunction.mockImplementation(
    async (_fn: string, _key: string, _machine: string, _params: unknown, options: unknown) => {
      await settle((options as { job: { steps: Planned[] } }).job.steps, LIMITS_STDOUT);
      return { success: true };
    }
  );
});

describe('repo policy get with a structured output format', () => {
  it.each(['json', 'yaml'] as const)('prints one merged %s document', async (format) => {
    mocks.format = format;
    await run();
    expect(mocks.print).toHaveBeenCalledTimes(1);
    expect(mocks.print).toHaveBeenCalledWith(
      {
        effective: { auto_grow: true },
        repo_override: null,
        limits: { pids_max: 4096 },
        ram_volume: { size: 1 },
      },
      format
    );
  });

  it('keeps the two tables in table output', async () => {
    mocks.format = 'table';
    await run();
    expect(mocks.print).toHaveBeenCalledTimes(2);
  });

  it('prints nothing, and runs no limits job, when the settings read is still pending', async () => {
    mocks.runCommandJob.mockResolvedValue({ kind: 'pending' });
    await run();
    expect(mocks.executeRepoFunction).not.toHaveBeenCalled();
    expect(mocks.print).not.toHaveBeenCalled();
  });
});
