/**
 * The finished-while-away notice and steps (section 18): interactive text runs
 * run owed steps; `-o json`, `-q` and MCP print the pending line and run nothing.
 */

import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  finishNotice,
  type NoticeDeps,
  noticeMode,
  printFinishedNotices,
  shouldRunNotice,
  startNoticeCheck,
} from '../finished-notice.js';
import type { ClaimExec, StepRunnerDeps } from '../run-job.js';
import { planStep, toTicketSteps } from '../steps.js';
import { TicketStore } from '../ticket-store.js';

const JOB_ID = 'j1a2b-0123abcd';
let base: string;
let store: TicketStore;

beforeEach(async () => {
  base = mkdtempSync(join(tmpdir(), 'rdc-steps-notice-'));
  store = new TicketStore('rediacc', base);
  const { initI18n } = await import('../../../i18n/index.js');
  await initI18n('en');
});
afterEach(() => {
  rmSync(base, { recursive: true, force: true });
});

function addFinished(state: 'succeeded' | 'failed' = 'succeeded'): void {
  store.append('starting', 'r1', {
    machine: 'm1',
    verb: 'repo up',
    repo: 'web',
    startedAt: '2026-01-01T00:00:00Z',
    steps: toTicketSteps([planStep('postRepoUpTasks', { repo: 'web', machine: 'm1' })]),
  });
  store.append('started', 'r1', { jobId: JOB_ID, via: { kind: 'ssh' } });
  store.append('finished', 'r1', { state, exitCode: state === 'succeeded' ? 0 : 1 });
}

function spyRunner(): { deps: StepRunnerDeps; claim: ReturnType<typeof vi.fn>; ran: string[] } {
  const ran: string[] = [];
  const claim = vi.fn<ClaimExec>(async ({ steps, done }) =>
    steps.map((name) => ({ name, result: done ? ('done' as const) : ('claimed' as const) }))
  );
  return {
    ran,
    claim,
    deps: {
      claim,
      observer: { configName: 'rediacc' },
      warn: vi.fn(),
      resolve: (name) =>
        Promise.resolve(() => {
          ran.push(name);
          return Promise.resolve();
        }),
    },
  };
}

describe('notice mode', () => {
  const base = { commandPath: 'repo up', quiet: false, format: 'table', inExecutorRequest: false };

  it('is full for a text run, pending-only under -o json or -q, off for job and executor requests', () => {
    expect(noticeMode(base)).toBe('full');
    expect(noticeMode({ ...base, format: 'json' })).toBe('pending-only');
    expect(noticeMode({ ...base, quiet: true })).toBe('pending-only');
    expect(noticeMode({ ...base, commandPath: 'job list' })).toBe('off');
    expect(noticeMode({ ...base, inExecutorRequest: true })).toBe('off');
  });
});

describe('the notice under -o json', () => {
  it('prints the pending line on stderr and runs nothing', async () => {
    addFinished();
    const runner = spyRunner();
    const stdout = vi.spyOn(process.stdout, 'write');
    const write = vi.fn();

    // MCP runs `rdc ... --output json --quiet`: the full check never starts.
    const full = shouldRunNotice({
      commandPath: 'repo up',
      quiet: true,
      format: 'json',
      inExecutorRequest: false,
    });
    expect(full).toBe(false);
    await finishNotice(() => ({ store, write }));

    expect(write).toHaveBeenCalledTimes(1);
    expect(write).toHaveBeenCalledWith(`steps pending: rdc job wait ${JOB_ID}`);
    expect(runner.claim).not.toHaveBeenCalled();
    expect(runner.ran).toEqual([]);
    expect(stdout).not.toHaveBeenCalled();
    stdout.mockRestore();
    // Still owed, so `rdc job list` keeps showing it.
    expect(store.pending()).toHaveLength(1);
  });

  it('prints nothing for a ticket that owes no step', async () => {
    addFinished('failed'); // postRepoUpTasks is a success step
    const write = vi.fn();
    shouldRunNotice({
      commandPath: 'repo up',
      quiet: false,
      format: 'json',
      inExecutorRequest: false,
    });
    await finishNotice(() => ({ store, write }));
    expect(write).not.toHaveBeenCalled();
  });

  it('a job command prints nothing', async () => {
    addFinished();
    const write = vi.fn();
    shouldRunNotice({
      commandPath: 'job list',
      quiet: false,
      format: 'json',
      inExecutorRequest: false,
    });
    await finishNotice(() => ({ store, write }));
    expect(write).not.toHaveBeenCalled();
  });
});

describe('the notice in a text run', () => {
  function noticeDeps(runner: StepRunnerDeps, interactive: boolean, write = vi.fn()): NoticeDeps {
    return { store, observe: async () => undefined, write, steps: runner, interactive };
  }

  it('runs the owed steps when interactive, then announces and acknowledges', async () => {
    addFinished();
    const runner = spyRunner();
    const write = vi.fn();
    shouldRunNotice({
      commandPath: 'repo up',
      quiet: false,
      format: 'table',
      inExecutorRequest: false,
    });
    startNoticeCheck(noticeDeps(runner.deps, true, write));
    await finishNotice();

    expect(runner.ran).toEqual(['postRepoUpTasks']);
    expect(write).toHaveBeenCalledTimes(1);
    expect(write.mock.calls[0][0]).toContain('succeeded');
    expect(store.find(JOB_ID)?.stepsDone).toEqual(['postRepoUpTasks']);
    expect(store.pending()).toEqual([]);
  });

  it('a non-interactive text run runs nothing and prints the pending line', async () => {
    addFinished();
    const runner = spyRunner();
    const write = vi.fn();
    shouldRunNotice({
      commandPath: 'repo up',
      quiet: false,
      format: 'table',
      inExecutorRequest: false,
    });
    startNoticeCheck(noticeDeps(runner.deps, false, write));
    await finishNotice();

    expect(runner.claim).not.toHaveBeenCalled();
    expect(write.mock.calls.map((c) => c[0])).toEqual([
      expect.stringContaining('succeeded'),
      `steps pending: rdc job wait ${JOB_ID}`,
    ]);
    expect(store.pending()).toHaveLength(1);
  });

  it('starts no step once the budget is spent', async () => {
    addFinished();
    const runner = spyRunner();
    let clock = 0;
    const deps: NoticeDeps = {
      ...noticeDeps(runner.deps, true),
      now: () => {
        clock += 30_000;
        return clock;
      },
    };
    const { runNoticeSteps } = await import('../finished-notice.js');
    await runNoticeSteps(deps, 20_000);
    expect(runner.claim).not.toHaveBeenCalled();
    printFinishedNotices(deps);
    expect(store.pending()).toHaveLength(1);
  });
});
