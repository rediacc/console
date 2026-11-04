/**
 * PLAN-detached-jobs J18: `config reconcile` runs one list-all job per machine under one group. Every machine's ticket
 * carries `recordMachineListing`, the group's last ticket also carries the one reconcile, and the reconcile reads the
 * listings from the group's scratch records. A machine whose job could not start leaves its error as its record, and a
 * last machine that could not start leaves no ticket for the final step, so the command settles the group itself.
 */
import { mkdtempSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setCommandJobDeps } from '../../services/jobs/command-job.js';
import { TicketStore } from '../../services/jobs/ticket-store.js';
import { installJobDeps } from './job-deps.js';

const mocks = vi.hoisted(() => ({
  print: vi.fn(),
  info: vi.fn(),
  setExitCode: vi.fn(),
  reconciled: [] as { seen: string[]; unreachable: { machine: string; error: string }[] }[],
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  getOutputFormat: () => 'json',
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { print: mocks.print, info: mocks.info, success: vi.fn(), warn: vi.fn() },
}));
vi.mock('../../services/core/request-context.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  setExitCode: mocks.setExitCode,
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getEffectiveConfigName: () => 'test',
    getCurrent: async () => ({
      resources: { machines: { m1: { ip: '10.0.0.1' }, m2: { ip: '10.0.0.2' } } },
    }),
  },
}));
vi.mock('../../services/machine/machine-status.js', () => ({
  machineStatusJob: async (machineName: string) => ({
    functionName: 'list-all',
    machineName,
    captureOutput: true,
  }),
  parseMachineStatus: (stdout: string) => JSON.parse(stdout),
}));
vi.mock('../../services/config/config-reconcile.js', () => ({
  reconcileState: async (deps: {
    loadConfig: () => Promise<{ resources: { machines: Record<string, unknown> } }>;
    fetchStatus: (m: string) => Promise<unknown>;
  }) => {
    const config = await deps.loadConfig();
    const seen: string[] = [];
    const unreachable: { machine: string; error: string }[] = [];
    for (const machine of Object.keys(config.resources.machines)) {
      try {
        await deps.fetchStatus(machine);
        seen.push(machine);
      } catch (error) {
        unreachable.push({ machine, error: (error as Error).message });
      }
    }
    mocks.reconciled.push({ seen, unreachable });
    return {
      reconciledAt: 't',
      machinesSeen: seen,
      machinesUnreachable: unreachable,
      placementsFilled: [],
      placementsAccepted: [],
      conflicts: [],
      networkIdsRebuilt: [],
      networkIdsDiverged: [],
    };
  },
}));

const { registerConfigCommands } = await import('../config.js');

type Executed = {
  machineName: string;
  jobSteps?: { name: string; on: string; params: Record<string, unknown> }[];
};

const listing = (machine: string) => ({
  success: true,
  exitCode: 0,
  durationMs: 1,
  state: 'succeeded' as const,
  jobId: `j-${machine}`,
  stdout: JSON.stringify({ machine }),
});

let executed: Executed[];
let answer: (machine: string) => Promise<Record<string, unknown>>;
let restoreJobDeps: () => void;
let configDir: string;
let prevXdg: string | undefined;

beforeEach(() => {
  vi.clearAllMocks();
  mocks.reconciled.length = 0;
  executed = [];
  answer = async (machine) => listing(machine);
  configDir = mkdtempSync(join(tmpdir(), 'reconcile-job-'));
  prevXdg = process.env.XDG_CONFIG_HOME;
  process.env.XDG_CONFIG_HOME = configDir;
  restoreJobDeps = installJobDeps((options) => {
    executed.push(options as unknown as Executed);
    return answer(options.machineName) as never;
  });
});

afterEach(() => {
  restoreJobDeps();
  if (prevXdg === undefined) delete process.env.XDG_CONFIG_HOME;
  else process.env.XDG_CONFIG_HOME = prevXdg;
  rmSync(configDir, { recursive: true, force: true });
});

async function reconcile(...argv: string[]) {
  const program = new Command();
  program.exitOverride();
  registerConfigCommands(program);
  await program.parseAsync(['config', 'reconcile', ...argv], { from: 'user' });
}

const stepNames = (e: Executed) => e.jobSteps?.map((s) => s.name);

describe('config reconcile as one job per machine under one group', () => {
  it('records each listing and reconciles once, after the last machine finished', async () => {
    await reconcile();
    expect(executed.map((e) => e.machineName)).toEqual(['m1', 'm2']);
    for (const e of executed) {
      expect(stepNames(e)).toEqual([
        'recordMachineListing',
        'reconcileConfigState',
        'reconcileConfigStateFailed',
      ]);
    }
    const groups = new Set(executed.flatMap((e) => e.jobSteps?.map((s) => s.params.group) ?? []));
    expect(groups.size).toBe(1);
    expect(mocks.reconciled).toEqual([{ seen: ['m1', 'm2'], unreachable: [] }]);
    expect(mocks.print).toHaveBeenCalledOnce();
    // The scratch records of the group are gone once it settled; only its claim marker stays, against a late second settle.
    const scratchRoot = join(configDir, 'rediacc', 'jobs', 'test.scratch');
    const [settled] = readdirSync(scratchRoot);
    expect(readdirSync(join(scratchRoot, settled))).toEqual(['settled.claim']);
  });

  it('a machine whose job could not start is unreachable, with its error, and the last machine still settles', async () => {
    answer = (machine) =>
      machine === 'm1'
        ? Promise.reject(new Error('ssh refused'))
        : Promise.resolve(listing(machine));
    await reconcile();
    expect(mocks.reconciled).toEqual([
      { seen: ['m2'], unreachable: [{ machine: 'm1', error: 'ssh refused' }] },
    ]);
  });

  it('a last machine that could not start leaves no ticket for the step, so the command settles', async () => {
    answer = (machine) =>
      machine === 'm2' ? Promise.reject(new Error('no route')) : Promise.resolve(listing(machine));
    await reconcile();
    expect(mocks.reconciled).toEqual([
      { seen: ['m1'], unreachable: [{ machine: 'm2', error: 'no route' }] },
    ]);
    expect(mocks.print).toHaveBeenCalledOnce();
  });

  it('a last job dispatched whose ticket then fails to record settles once: the ticket steps find the claim taken (f5138b83.1, f5b87d0e.2)', async () => {
    restoreJobDeps();
    const dir = mkdtempSync(join(tmpdir(), 'reconcile-dispatched-'));
    const store = new TicketStore('test', dir);
    let dispatched = false;
    const append = store.append.bind(store);
    store.append = ((...args: Parameters<typeof append>) => {
      if (dispatched) throw new Error('disk full');
      return append(...args);
    }) as typeof store.append;
    setCommandJobDeps({
      executor: () => ({
        execute: (options: { machineName: string }) => {
          executed.push(options as unknown as Executed);
          if (options.machineName === 'm2') dispatched = true;
          return Promise.resolve(listing(options.machineName) as never);
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
    restoreJobDeps = () => {
      setCommandJobDeps();
      rmSync(dir, { recursive: true, force: true });
    };
    await reconcile();
    // The command settled the group (m2 as unreachable with the recording error), and nothing settles it again.
    expect(mocks.reconciled).toHaveLength(1);
    expect(mocks.reconciled[0].unreachable.map((u) => u.machine)).toEqual(['m2']);
    expect(mocks.print).toHaveBeenCalledOnce();
    // The late ticket of m2 runs its steps now: a second settlement would reconcile again.
    const { resolveStepHandler } = await import('../../services/jobs/steps.js');
    const group = executed[0].jobSteps?.[0].params.group;
    const ctx = { jobId: 'j-m2', machine: 'm2', state: 'succeeded' as const, output: '{}' };
    const params = executed[1].jobSteps?.find((x) => x.name === 'reconcileConfigState')?.params;
    await (await resolveStepHandler('recordMachineListing'))({
      ...ctx,
      params: { group },
    } as never);
    await (await resolveStepHandler('reconcileConfigState'))({ ...ctx, params } as never);
    expect(mocks.reconciled).toHaveLength(1);
    expect(mocks.print).toHaveBeenCalledOnce();
  });

  it('a last job that failed settles through the failure step, once', async () => {
    answer = async (machine) =>
      machine === 'm2'
        ? { success: false, exitCode: 3, durationMs: 1, state: 'failed', jobId: 'j-m2' }
        : listing(machine);
    await reconcile();
    expect(mocks.reconciled).toHaveLength(1);
    expect(mocks.reconciled[0].seen).toEqual(['m1']);
    expect(mocks.reconciled[0].unreachable[0].machine).toBe('m2');
  });

  it('waits for a machine still running: nothing reconciles and no record is dropped', async () => {
    answer = async (machine) =>
      machine === 'm1'
        ? { success: true, exitCode: 0, durationMs: 1, state: 'running', jobId: 'j-m1' }
        : listing(machine);
    await reconcile();
    expect(mocks.reconciled).toEqual([]);
    expect(mocks.print).not.toHaveBeenCalled();
    expect(readdirSync(join(configDir, 'rediacc', 'jobs', 'test.scratch'))).toHaveLength(1);
  });

  it('--machine narrows both the jobs and the reconcile', async () => {
    await reconcile('--machine', 'm1');
    expect(executed.map((e) => e.machineName)).toEqual(['m1']);
    expect(stepNames(executed[0])).toContain('reconcileConfigState');
    expect(mocks.reconciled).toEqual([{ seen: ['m1'], unreachable: [] }]);
  });
});
