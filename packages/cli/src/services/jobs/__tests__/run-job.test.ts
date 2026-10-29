import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { JobStatus } from '../../executor/job-client.js';
import { runNoticeSteps } from '../finished-notice.js';
import { type JobWaitDeps, waitForJob } from '../job-wait.js';
import {
  buildJobClaimCommand,
  type ClaimExec,
  type ConfigIdentity,
  configMatches,
  type JobCall,
  parseClaimOutput,
  runJob,
  runTicketSteps,
  type StepRunnerDeps,
} from '../run-job.js';
import { type PlannedStep, planStep, type StepHandler, toTicketSteps } from '../steps.js';
import { type Ticket, type TicketState, TicketStore } from '../ticket-store.js';

const JOB_ID = 'j1a2b-0123abcd';
let base: string;
let store: TicketStore;

beforeEach(async () => {
  base = mkdtempSync(join(tmpdir(), 'rdc-run-job-'));
  store = new TicketStore('rediacc', base);
  const { initI18n } = await import('../../../i18n/index.js');
  await initI18n('en');
});
afterEach(() => {
  rmSync(base, { recursive: true, force: true });
});

/** renet's claim semantics: O_EXCL claim, then done. Shared by every observer of one machine. */
function fakeMachine() {
  const claimed = new Set<string>();
  const done = new Set<string>();
  const calls: { steps: string[]; done?: boolean }[] = [];
  const claim: ClaimExec = async ({ jobId, steps, done: markDone }) => {
    calls.push({ steps, done: markDone });
    await new Promise((r) => setTimeout(r, 1));
    return steps.map((name) => {
      const key = `${jobId}/${name}`;
      if (markDone) {
        done.add(key);
        return { name, result: 'done' as const };
      }
      if (done.has(key)) return { name, result: 'done' as const };
      if (claimed.has(key)) return { name, result: 'already-claimed' as const };
      claimed.add(key);
      return { name, result: 'claimed' as const };
    });
  };
  return { claim, calls, done };
}

function handlers(names: string[], delayMs = 0) {
  const ran: string[] = [];
  const fns: Record<string, StepHandler> = {};
  for (const name of names) {
    fns[name] = async () => {
      if (delayMs) await new Promise((r) => setTimeout(r, delayMs));
      ran.push(name);
    };
  }
  return { ran, resolve: async (name: string) => fns[name] };
}

function stepDeps(
  claim: ClaimExec,
  resolve: (name: string) => Promise<StepHandler>,
  observer: ConfigIdentity = { configName: 'rediacc' }
): StepRunnerDeps {
  return { claim, resolve, observer, warn: vi.fn() };
}

function addTicket(steps: PlannedStep[], state?: TicketState): Ticket {
  store.append('starting', 'r1', {
    machine: 'm1',
    verb: 'repo up',
    repo: 'web',
    startedAt: '2026-01-01T00:00:00Z',
    steps: toTicketSteps(steps),
  });
  store.append('started', 'r1', { jobId: JOB_ID, via: { kind: 'ssh' } });
  if (state) store.append('finished', 'r1', { state, exitCode: state === 'succeeded' ? 0 : 1 });
  return store.find(JOB_ID) as Ticket;
}

const UP = () => planStep('postRepoUpTasks', { repo: 'web', machine: 'm1' });
const ROLLBACK = () => planStep('rollbackCreate', { repo: 'web' });

describe('exactly once', () => {
  it('two concurrent observers (job wait and the notice) run a success step once', async () => {
    addTicket([UP()], 'succeeded');
    const machine = fakeMachine();
    const h = handlers(['postRepoUpTasks'], 20);
    const deps = stepDeps(machine.claim, h.resolve);

    const waitDeps: JobWaitDeps = {
      withConnection: (_m, fn) => fn({}),
      follow: async () => false,
      readStatus: async () => ({}) as JobStatus,
      steps: deps,
    };
    const otherStore = new TicketStore('rediacc', base);
    await Promise.all([
      waitForJob(store, store.find(JOB_ID) as Ticket, waitDeps, { onEvent: () => {} }),
      runNoticeSteps({
        store: otherStore,
        observe: async () => undefined,
        write: vi.fn(),
        steps: deps,
      }),
    ]);

    expect(h.ran).toEqual(['postRepoUpTasks']);
    expect(machine.done.has(`${JOB_ID}/postRepoUpTasks`)).toBe(true);
  });

  it('records step-done, and a later observer runs nothing', async () => {
    const ticket = addTicket([UP()], 'succeeded');
    const machine = fakeMachine();
    const h = handlers(['postRepoUpTasks']);

    const first = await runTicketSteps(
      store,
      ticket,
      { state: 'succeeded' },
      stepDeps(machine.claim, h.resolve)
    );
    expect(first.ran).toEqual(['postRepoUpTasks']);
    expect(store.find(JOB_ID)?.stepsDone).toEqual(['postRepoUpTasks']);
    const lines = readFileSync(store.path, 'utf8')
      .trim()
      .split('\n')
      .map((l) => JSON.parse(l));
    expect(lines.filter((l) => l.kind === 'step-done')).toEqual([
      expect.objectContaining({ step: 'postRepoUpTasks', requestId: 'r1' }),
    ]);

    machine.calls.length = 0;
    const again = await runTicketSteps(
      store,
      store.find(JOB_ID) as Ticket,
      { state: 'succeeded' },
      stepDeps(machine.claim, h.resolve)
    );
    expect(again.ran).toEqual([]);
    expect(machine.calls).toEqual([]);
    expect(h.ran).toEqual(['postRepoUpTasks']);
  });

  it('mirrors a step another observer finished as done, without running it', async () => {
    const ticket = addTicket([UP()], 'succeeded');
    const machine = fakeMachine();
    await machine.claim({ machine: 'm1', jobId: JOB_ID, steps: ['postRepoUpTasks'] });
    await machine.claim({ machine: 'm1', jobId: JOB_ID, steps: ['postRepoUpTasks'], done: true });
    const h = handlers(['postRepoUpTasks']);

    const report = await runTicketSteps(
      store,
      ticket,
      { state: 'succeeded' },
      stepDeps(machine.claim, h.resolve)
    );
    expect(h.ran).toEqual([]);
    expect(report.doneElsewhere).toEqual(['postRepoUpTasks']);
    expect(store.find(JOB_ID)?.stepsDone).toEqual(['postRepoUpTasks']);
  });

  it('a failing handler leaves the step pending and unmarked on the machine', async () => {
    const ticket = addTicket([UP()], 'succeeded');
    const machine = fakeMachine();
    const deps = stepDeps(machine.claim, () =>
      Promise.resolve(() => Promise.reject(new Error('dns down')))
    );
    const report = await runTicketSteps(store, ticket, { state: 'succeeded' }, deps);
    expect(report.failed).toEqual(['postRepoUpTasks']);
    expect(deps.warn).toHaveBeenCalledWith('dns down');
    expect(machine.done.size).toBe(0);
    expect(store.find(JOB_ID)?.stepsDone).toEqual([]);
  });
});

describe('success and failure', () => {
  it('a success step never runs on a failed job', async () => {
    const ticket = addTicket([UP(), ROLLBACK()], 'failed');
    const machine = fakeMachine();
    const h = handlers(['postRepoUpTasks', 'rollbackCreate']);
    await runTicketSteps(store, ticket, { state: 'failed' }, stepDeps(machine.claim, h.resolve));
    expect(h.ran).toEqual(['rollbackCreate']);
    expect(machine.calls.flatMap((c) => c.steps)).not.toContain('postRepoUpTasks');
  });

  it('a failure step never runs on a succeeded job', async () => {
    const ticket = addTicket([UP(), ROLLBACK()], 'succeeded');
    const machine = fakeMachine();
    const h = handlers(['postRepoUpTasks', 'rollbackCreate']);
    await runTicketSteps(store, ticket, { state: 'succeeded' }, stepDeps(machine.claim, h.resolve));
    expect(h.ran).toEqual(['postRepoUpTasks']);
    expect(machine.calls.flatMap((c) => c.steps)).not.toContain('rollbackCreate');
  });

  it('a cancelled job runs the failure step', async () => {
    const ticket = addTicket([UP(), ROLLBACK()], 'cancelled');
    const machine = fakeMachine();
    const h = handlers(['postRepoUpTasks', 'rollbackCreate']);
    await runTicketSteps(store, ticket, { state: 'cancelled' }, stepDeps(machine.claim, h.resolve));
    expect(h.ran).toEqual(['rollbackCreate']);
  });
});

describe('config gate', () => {
  it('an observer of another config runs nothing and claims nothing', async () => {
    const ticket = addTicket([UP()], 'succeeded');
    const machine = fakeMachine();
    const h = handlers(['postRepoUpTasks']);
    const report = await runTicketSteps(
      store,
      ticket,
      { state: 'succeeded' },
      stepDeps(machine.claim, h.resolve, { configName: 'other' })
    );
    expect(report.gated).toEqual(['postRepoUpTasks']);
    expect(h.ran).toEqual([]);
    expect(machine.calls).toEqual([]);
  });

  it('the job origin decides over the ticket, and ids decide over names', async () => {
    const ticket = addTicket([UP()], 'succeeded');
    const machine = fakeMachine();
    const h = handlers(['postRepoUpTasks']);
    const report = await runTicketSteps(
      store,
      ticket,
      { state: 'succeeded', origin: { configName: 'rediacc', configId: 'id-a' } },
      stepDeps(machine.claim, h.resolve, { configName: 'rediacc', configId: 'id-b' })
    );
    expect(report.gated).toEqual(['postRepoUpTasks']);
    expect(h.ran).toEqual([]);

    expect(configMatches({ configId: 'a' }, { configId: 'a', configName: 'x' })).toBe(true);
    expect(configMatches({ configName: 'a' }, { configName: 'b' })).toBe(false);
  });

  it('the notice prints the pending-for-config line for a gated ticket', async () => {
    addTicket([UP()], 'succeeded');
    const machine = fakeMachine();
    const h = handlers(['postRepoUpTasks']);
    const write = vi.fn();
    await runNoticeSteps({
      store,
      observe: async () => undefined,
      write,
      steps: stepDeps(machine.claim, h.resolve, { configName: 'other' }),
    });
    expect(h.ran).toEqual([]);
    expect(write).toHaveBeenCalledWith('1 steps pending for config rediacc');
  });
});

describe('the marker-triggered step', () => {
  function migrateCall(markers: string[]): JobCall<string> {
    return {
      verb: 'repo migrate',
      function: 'repository_migrate',
      machine: 'm1',
      repo: 'web',
      start: async () => ({ kind: 'pending', jobId: JOB_ID, job: { state: 'running', markers } }),
    };
  }

  it('runs on the cutover_complete marker while the job is still running', async () => {
    const machine = fakeMachine();
    const h = handlers(['migratePlacement']);
    const result = await runJob(
      migrateCall(['push', 'cutover_complete']),
      [planStep('migratePlacement', { repo: 'web', machine: 'm2' })],
      { store, steps: stepDeps(machine.claim, h.resolve), mintRequestId: () => 'r1' }
    );
    expect(result.kind).toBe('pending');
    expect(h.ran).toEqual(['migratePlacement']);
    expect(store.find(JOB_ID)?.stepsDone).toEqual(['migratePlacement']);
  });

  it('does not run before the marker, and not on success-only grounds while running', async () => {
    const machine = fakeMachine();
    const h = handlers(['migratePlacement', 'postRepoUpTasks']);
    await runJob(
      migrateCall(['push']),
      [planStep('migratePlacement', { repo: 'web', machine: 'm2' }), UP()],
      { store, steps: stepDeps(machine.claim, h.resolve), mintRequestId: () => 'r1' }
    );
    expect(h.ran).toEqual([]);
    expect(machine.calls).toEqual([]);
  });
});

describe('runJob', () => {
  it('writes starting before the start, hands the spool plan to the call, and finishes inline', async () => {
    const machine = fakeMachine();
    const h = handlers(['postRepoUpTasks']);
    const seen: unknown[] = [];
    const call: JobCall<{ ok: true }> = {
      verb: 'repo up',
      function: 'repository_up',
      machine: 'm1',
      repo: 'web',
      start: (request) => {
        seen.push(request, store.tickets()[0]?.state);
        return Promise.resolve({
          kind: 'finished',
          jobId: JOB_ID,
          result: { ok: true },
          job: { state: 'succeeded', exitCode: 0 },
        } as const);
      },
    };
    const result = await runJob(call, [UP()], {
      store,
      steps: stepDeps(machine.claim, h.resolve),
      mintRequestId: () => 'r1',
    });

    expect(seen[0]).toEqual({
      requestId: 'r1',
      steps: [{ name: 'postRepoUpTasks', on: 'success', params: { repo: 'web', machine: 'm1' } }],
    });
    expect(seen[1]).toBe('starting');
    expect(result.kind).toBe('finished');
    if (result.kind === 'finished') expect(result.result).toEqual({ ok: true });
    expect(h.ran).toEqual(['postRepoUpTasks']);
    // Ran inline: nothing is left for the notice or `rdc job list`.
    expect(store.pending()).toEqual([]);
  });

  it('returns pending(ticket) when the job outlasts the attach', async () => {
    const machine = fakeMachine();
    const h = handlers(['postRepoUpTasks']);
    const result = await runJob(
      {
        verb: 'repo up',
        function: 'repository_up',
        machine: 'm1',
        start: async () => ({ kind: 'pending', jobId: JOB_ID, lastSeenLine: 7 }),
      },
      [UP()],
      { store, steps: stepDeps(machine.claim, h.resolve), mintRequestId: () => 'r1' }
    );
    expect(result.kind).toBe('pending');
    expect(result.ticket).toMatchObject({ jobId: JOB_ID, state: 'running', lastSeenLine: 7 });
    expect(result.ticket.steps.map((s) => s.name)).toEqual(['postRepoUpTasks']);
    expect(h.ran).toEqual([]);
    expect(machine.calls).toEqual([]);
  });
});

describe('the claim command', () => {
  it('quotes the origin and host and refuses a bad step name', () => {
    const cmd = buildJobClaimCommand({
      remoteRenetPath: '/usr/bin/renet',
      jobId: JOB_ID,
      steps: ['postRepoUpTasks', 'recordBackupRun'],
      done: true,
      origin: { configName: 'rediacc', configId: 'abc' },
      host: "lap'top",
      pid: 42,
    });
    expect(cmd).toContain(
      `job claim --id ${JOB_ID} --steps postRepoUpTasks,recordBackupRun --done`
    );
    expect(cmd).toContain(`'{"client":"rdc","config":{"name":"rediacc","id":"abc"}}'`);
    expect(cmd).toContain('--pid 42');
    expect(() =>
      buildJobClaimCommand({
        remoteRenetPath: 'r',
        jobId: JOB_ID,
        steps: ['a;rm -rf /'],
        origin: {},
        host: 'h',
        pid: 1,
      })
    ).toThrow(/Invalid step name/);
  });

  it('parses the claim answer', () => {
    expect(
      parseClaimOutput(
        '{"job_id":"j1","steps":[{"name":"a","result":"claimed"},{"name":"b","result":"already-claimed","claimant":{}},{"name":"c","result":"bogus"}]}'
      )
    ).toEqual([
      { name: 'a', result: 'claimed' },
      { name: 'b', result: 'already-claimed' },
    ]);
  });
});
