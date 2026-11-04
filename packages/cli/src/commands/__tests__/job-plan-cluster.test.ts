/**
 * PLAN-detached-jobs J19: a datastore verb is one machine job whose config record rides the ticket as a step.
 *
 * `datastore resize` and `datastore create` are the converted rows here. The executor is a recording fake behind the
 * runCommandJob seam, the ticket store is real in a temp directory, and the step claim grants every claim, so the
 * test sees each command's own plan: one `job start` per verb, the record as a success step, and no config write
 * from the command body itself.
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

const m = vi.hoisted(() => ({
  getDatastore: vi.fn(),
  recordDatastore: vi.fn().mockResolvedValue(undefined),
  listDatastores: vi.fn().mockResolvedValue({}),
  requireDatastoreHost: vi.fn().mockResolvedValue('m1'),
  success: vi.fn(),
}));
vi.mock('../../services/config/config-datastores.js', () => ({
  assertCreatableName: vi.fn(),
  at: (state: Record<string, unknown>, ref: string) => state[ref],
  getDatastore: m.getDatastore,
  listDatastores: m.listDatastores,
  listDatastoreState: vi.fn().mockResolvedValue({}),
  parseDatastoreRef: (ref: string) => ({ name: ref }),
  recordDatastore: m.recordDatastore,
  requireDatastoreHost: m.requireDatastoreHost,
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getCurrent: vi.fn().mockResolvedValue({}), listClusters: vi.fn() },
}));
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: () => Promise.reject(new Error('the executor is replaced')) }),
}));
vi.mock('../../services/executor/local-executor.js', () => ({ parseCapturedJson: JSON.parse }));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn().mockResolvedValue(undefined),
  CMD: { DATASTORE_RESIZE: 'datastore resize', DATASTORE_CREATE: 'datastore create' },
}));
vi.mock('../_validate.js', () => ({ assertMachineExists: vi.fn().mockResolvedValue(undefined) }));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: m.success, warn: vi.fn(), print: vi.fn() },
}));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  getOutputFormat: () => 'table',
  handleError: (e: unknown) => {
    throw e;
  },
}));

const { registerDatastoreCommands } = await import('../datastore.js');
const { setCommandJobDeps } = await import('../../services/jobs/command-job.js');
const { TicketStore } = await import('../../services/jobs/ticket-store.js');
const { resolveStepHandler } = await import('../../services/jobs/steps.js');

type Executed = {
  functionName: string;
  machineName: string;
  params: Record<string, unknown>;
  jobSteps?: { name: string; on: string; params: Record<string, unknown> }[];
};

const BACKGROUND = {
  success: true,
  exitCode: 0,
  durationMs: 0,
  state: 'running' as const,
  jobId: 'job-1',
  attached: false,
};
const FINISHED = { ...BACKGROUND, durationMs: 5, state: 'succeeded' as const, attached: true };
const FAILED = { ...FINISHED, success: false, exitCode: 1, state: 'failed' as const };

let dir: string;
let store: InstanceType<typeof TicketStore>;
let executed: Executed[];
let answer: Record<string, unknown>;

async function run(...argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerDatastoreCommands(program);
  await program.parseAsync(['node', 'rdc', 'datastore', ...argv]);
}

beforeEach(() => {
  vi.clearAllMocks();
  m.getDatastore.mockResolvedValue({
    backend: { kind: 'local', machine: 'm1', path: '/x' },
    size: '1G',
  });
  m.requireDatastoreHost.mockResolvedValue('m1');
  dir = mkdtempSync(join(tmpdir(), 'job-plan-cluster-'));
  store = new TicketStore('test', dir);
  executed = [];
  answer = FINISHED;
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

describe('datastore resize (one job; the record as a success step)', () => {
  it('makes one job start on the holder with the record planned, not written by the command', async () => {
    answer = BACKGROUND;
    await run('resize', 'tier1', '--size', '2G');

    expect(executed).toHaveLength(1);
    expect(executed[0]).toMatchObject({
      functionName: 'datastore_resize',
      machineName: 'm1',
      params: { name: 'tier1', size: '2G' },
    });
    expect(executed[0].jobSteps?.map((s) => [s.name, s.on])).toEqual([
      ['recordDatastore', 'success'],
    ]);
    // A job still running owes the record to its ticket; nothing is written and no success is claimed.
    expect(m.recordDatastore).not.toHaveBeenCalled();
    expect(m.success).not.toHaveBeenCalled();
    expect(store.tickets()[0].steps.map((s) => s.name)).toEqual(['recordDatastore']);
  });

  it('control: followed, the record is written once with the new size', async () => {
    await run('resize', 'tier1', '--size', '2G');
    expect(m.recordDatastore).toHaveBeenCalledExactlyOnceWith('tier1', {
      backend: { kind: 'local', machine: 'm1', path: '/x' },
      size: '2G',
    });
    expect(m.success).toHaveBeenCalledOnce();
  });

  it('a failed job throws and records nothing', async () => {
    answer = FAILED;
    await expect(run('resize', 'tier1', '--size', '2G')).rejects.toThrow(/datastore_resize/);
    expect(m.recordDatastore).not.toHaveBeenCalled();
  });
});

describe('datastore create (one job; the record as a success step)', () => {
  it('records the new datastore only through the ticket step', async () => {
    answer = BACKGROUND;
    await run('create', 'tier2', '-m', 'm1', '--size', '10G');

    expect(executed.map((o) => o.functionName)).toEqual(['datastore_create']);
    const ticket = store.tickets()[0];
    expect(ticket.steps.map((s) => s.name)).toEqual(['recordDatastore']);
    expect(m.recordDatastore).not.toHaveBeenCalled();

    // The observer that sees the job finish runs the step from the ticket's recorded params.
    const step = ticket.steps[0];
    const handler = await resolveStepHandler('recordDatastore');
    await handler({
      jobId: 'job-1',
      machine: 'm1',
      params: step.params ?? {},
      state: 'succeeded',
    });
    expect(m.recordDatastore).toHaveBeenCalledExactlyOnceWith('tier2', {
      backend: { kind: 'local', machine: 'm1', path: '/mnt/rediacc-ds/tier2' },
      size: '10G',
    });
  });
});
