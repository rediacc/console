import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { observeTerminalPoll } from '../executor-observation.js';
import type { StepRunnerDeps } from '../run-job.js';
import { TicketStore } from '../ticket-store.js';

const JOB = 'j18c1c04dd251ce26-0ccf9fe5';

describe('observeTerminalPoll', () => {
  const dirs: string[] = [];
  afterEach(() => {
    for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
  });

  function setup() {
    const dir = mkdtempSync(join(tmpdir(), 'observe-'));
    dirs.push(dir);
    const store = new TicketStore('cfg', dir);
    store.append('starting', 'req-1', {
      verb: 'repo up',
      machine: 'prod-1',
      steps: [{ name: 'recordPushBase', on: 'success', params: {} }],
    });
    store.append('started', 'req-1', { jobId: JOB });
    const handler = vi.fn(() => Promise.resolve());
    const claim = vi.fn(() =>
      Promise.resolve([{ name: 'recordPushBase', result: 'claimed' as const }])
    );
    const stepDeps: StepRunnerDeps = {
      claim,
      observer: { configName: 'cfg' },
      warn: () => undefined,
      resolve: () => Promise.resolve(handler),
    };
    return {
      store,
      handler,
      claim,
      deps: { store: () => store, stepDeps: () => Promise.resolve(stepDeps) },
    };
  }

  it('runs the success step once across three polls of a finished job, then acknowledges', async () => {
    const { store, handler, deps } = setup();
    await observeTerminalPoll(JOB, { state: 'running' }, deps);
    expect(handler).not.toHaveBeenCalled();
    await observeTerminalPoll(JOB, { state: 'succeeded', exitCode: 0 }, deps);
    await observeTerminalPoll(JOB, { state: 'succeeded', exitCode: 0 }, deps);
    expect(handler).toHaveBeenCalledTimes(1);
    expect(store.find('req-1')).toMatchObject({ state: 'succeeded', acknowledged: true });
  });

  it('runs no success step for a failed job', async () => {
    const { handler, deps } = setup();
    await observeTerminalPoll(JOB, { state: 'failed', exitCode: 1 }, deps);
    expect(handler).not.toHaveBeenCalled();
  });

  it('owes nothing for a job the executor holds no ticket for, and never throws', async () => {
    const { deps } = setup();
    await expect(
      observeTerminalPoll('j0000000000000000-aaaaaaaa', { state: 'succeeded' }, deps)
    ).resolves.toBeUndefined();
    await expect(
      observeTerminalPoll(
        JOB,
        { state: 'succeeded' },
        {
          ...deps,
          store: () => {
            throw new Error('boom');
          },
        }
      )
    ).resolves.toBeUndefined();
  });
});
