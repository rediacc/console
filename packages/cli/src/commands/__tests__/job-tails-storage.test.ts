/**
 * PLAN-detached-jobs J4: `backup snapshot` and `backup verify` run one machine job each and record their run, and for
 * verify print the verdict, as ticket steps. Under `--background` the command returns at the job start with the steps
 * on the ticket and nothing recorded or printed; followed, the steps run in-process exactly once, and a failed job
 * records the failure the way its failure step declares (the renet quota refusal as `quota-refused`).
 *
 * The executor is a recording fake behind the runCommandJob seam through the real executeRepoFunction, the ticket store
 * is real (in a temp directory) and the step claim grants every claim.
 */
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockGetRepository = vi.hoisted(() => vi.fn());
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: vi.fn().mockResolvedValue({ resources: { repositories: { shop: {} } } }),
    getRepository: mockGetRepository,
    getRepositoryKey: (ref: string) => Promise.resolve(ref),
  },
}));
vi.mock('../../services/config/network-id-discovery.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/config/network-id-discovery.js')>()),
  ensureRepositoryNetworkId: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: () =>
    Promise.resolve({ name: 'shop', repoKey: 'shop', machineName: 'm1', tag: 'latest' }),
  resolveRepoRefLocal: () =>
    Promise.resolve({ name: 'shop', repoKey: 'shop', machineName: 'm1', tag: 'latest' }),
}));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: vi.fn() }));
const mockRecordBackupRun = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../../services/backup/backup-runs-state.js', () => ({
  recordBackupRun: mockRecordBackupRun,
}));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
const mockPrint = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    print: mockPrint,
    setTimelineRendered: vi.fn(),
    getCommandName: () => undefined,
  },
}));
vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return {
    ...actual,
    getOutputFormat: () => 'table',
    handleError: (e: unknown) => {
      throw e;
    },
  };
});

const { setCommandJobDeps } = await import('../../services/jobs/command-job.js');
const { TicketStore } = await import('../../services/jobs/ticket-store.js');
const { registerBackupStorageCommands } = await import('../backup-storage.js');

type Executed = Record<string, unknown> & { functionName: string; jobSteps?: { name: string }[] };

const VERDICT = { status: 'verified', level: 'spot', checked: 3 };
const FINISHED = {
  success: true,
  exitCode: 0,
  durationMs: 5,
  state: 'succeeded' as const,
  jobId: 'job-1',
  attached: true,
  stdout: `${JSON.stringify(VERDICT)}\n`,
};
const BACKGROUND = {
  success: true,
  exitCode: 0,
  durationMs: 0,
  state: 'running' as const,
  jobId: 'job-1',
  attached: false,
};
const FAILED = { ...FINISHED, success: false, exitCode: 1, state: 'failed' as const };

let dir: string;
let store: InstanceType<typeof TicketStore>;
let executed: Executed[];
let answer: Record<string, unknown>;

beforeEach(() => {
  vi.clearAllMocks();
  dir = mkdtempSync(join(tmpdir(), 'job-tails-storage-'));
  store = new TicketStore('test', dir);
  executed = [];
  answer = FINISHED;
  mockGetRepository.mockResolvedValue({ repositoryGuid: 'g-shop', networkId: 7, credential: 'c' });
  setCommandJobDeps({
    executor: () => ({
      execute: (options) => {
        executed.push(options as unknown as Executed);
        return Promise.resolve(answer as never);
      },
    }),
    store: () => store,
    stepDeps: () =>
      Promise.resolve({
        observer: { configName: 'test' },
        warn: () => undefined,
        claim: ({ steps }) =>
          Promise.resolve(steps.map((name) => ({ name, result: 'claimed' as const }))),
      }),
  });
});

afterEach(() => {
  setCommandJobDeps();
  rmSync(dir, { recursive: true, force: true });
  process.exitCode = 0;
});

async function runBackup(argv: string[]): Promise<void> {
  const backup = new Command('backup');
  backup.exitOverride();
  registerBackupStorageCommands(backup);
  await backup.parseAsync(argv, { from: 'user' });
}

function onlyTicket() {
  const tickets = store.tickets();
  expect(tickets).toHaveLength(1);
  return tickets[0];
}

const SNAPSHOT_STEPS = ['recordBackupRun', 'recordBackupRunFailed'] as const;
const VERIFY_STEPS = [
  'reportVerifyVerdict',
  'recordVerifyVerdict',
  'recordVerifyVerdictFailed',
] as const;

describe('backup snapshot (a finalizer pair: recordBackupRun, recordBackupRunFailed)', () => {
  it('under --background returns at the job start, with nothing recorded', async () => {
    answer = BACKGROUND;
    await runBackup(['snapshot', 'shop']);

    expect(executed.map((o) => o.functionName)).toEqual(['backup_snapshot']);
    expect(executed[0].jobSteps?.map((s) => s.name)).toEqual(SNAPSHOT_STEPS);
    expect(mockRecordBackupRun).not.toHaveBeenCalled();
    const ticket = onlyTicket();
    expect(ticket.steps.map((s) => s.name)).toEqual(SNAPSHOT_STEPS);
    expect(ticket.stepsDone).toEqual([]);
  });

  it('control: followed, the stored run is recorded exactly once', async () => {
    await runBackup(['snapshot', 'shop']);

    expect(mockRecordBackupRun).toHaveBeenCalledTimes(1);
    expect(mockRecordBackupRun).toHaveBeenCalledWith(
      'shop',
      expect.objectContaining({ kind: 'snapshot', status: 'stored' })
    );
    expect(onlyTicket().stepsDone).toEqual(['recordBackupRun']);
  });

  it('a failed snapshot records `failed`, and the renet quota refusal records `quota-refused`', async () => {
    answer = FAILED;
    await runBackup(['snapshot', 'shop']);
    expect(mockRecordBackupRun).toHaveBeenLastCalledWith(
      'shop',
      expect.objectContaining({ kind: 'snapshot', status: 'failed' })
    );

    answer = { ...FAILED, exitCode: 16 };
    await runBackup(['snapshot', 'shop']);
    expect(mockRecordBackupRun).toHaveBeenLastCalledWith(
      'shop',
      expect.objectContaining({ kind: 'snapshot', status: 'quota-refused' })
    );
    expect(mockRecordBackupRun).toHaveBeenCalledTimes(2);
  });

  it('control: --dry-run plans no step and records nothing', async () => {
    await runBackup(['snapshot', 'shop', '--dry-run']);

    expect(executed[0].jobSteps ?? []).toEqual([]);
    expect(mockRecordBackupRun).not.toHaveBeenCalled();
  });
});

describe('backup verify (a success step that prints, and a record that reads the verdict)', () => {
  it('under --background returns at the job start, printing and recording nothing', async () => {
    answer = BACKGROUND;
    await runBackup(['verify', 'shop']);

    expect(executed.map((o) => o.functionName)).toEqual(['backup_verify']);
    expect(executed[0].params).toMatchObject({ level: 'spot' });
    expect(executed[0].jobSteps?.map((s) => s.name)).toEqual(VERIFY_STEPS);
    expect(mockPrint).not.toHaveBeenCalled();
    expect(mockRecordBackupRun).not.toHaveBeenCalled();
    expect(onlyTicket().steps.map((s) => s.name)).toEqual(VERIFY_STEPS);
    expect(onlyTicket().stepsDone).toEqual([]);
  });

  it('control: followed, the verdict is printed once and the run is recorded once with its status', async () => {
    await runBackup(['verify', 'shop']);

    expect(mockPrint).toHaveBeenCalledExactlyOnceWith(VERDICT, 'json');
    expect(mockRecordBackupRun).toHaveBeenCalledExactlyOnceWith(
      'shop',
      expect.objectContaining({ kind: 'verify', status: 'verified' })
    );
  });

  it('a failed verify records the verdict the job reported, and prints no second document', async () => {
    answer = {
      ...FAILED,
      stdout: `${JSON.stringify({ status: 'mismatch', level: 'spot' })}\n`,
    };
    await runBackup(['verify', 'shop']);

    expect(mockRecordBackupRun).toHaveBeenCalledExactlyOnceWith(
      'shop',
      expect.objectContaining({ kind: 'verify', status: 'mismatch' })
    );
    expect(mockPrint).not.toHaveBeenCalled();
  });
});
