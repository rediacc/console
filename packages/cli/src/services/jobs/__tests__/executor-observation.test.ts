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

  describe('a create job whose ticket was lost with the container disk', () => {
    const GUID = '11111111-2222-4333-8444-555555555555';
    const lost = { function: 'repository_create', repoGuid: GUID };

    function rebuild(repoRef: string | undefined) {
      const { deps } = setup();
      const handler = vi.fn(() => Promise.resolve());
      const repoRefForGuid = vi.fn(() => Promise.resolve(repoRef));
      return {
        handler,
        repoRefForGuid,
        deps: { ...deps, resolve: () => Promise.resolve(handler), repoRefForGuid },
      };
    }
    const UNKNOWN_JOB = 'j0000000000000000-aaaaaaaa';

    it.each(['failed', 'cancelled'] as const)(
      'rolls the registration back from the job record when the job %s',
      async (state) => {
        const { deps, handler } = rebuild('shop');
        await observeTerminalPoll(UNKNOWN_JOB, { state, exitCode: 1, ...lost }, deps);
        expect(handler).toHaveBeenCalledOnce();
        expect(handler).toHaveBeenCalledWith(
          expect.objectContaining({ params: { repo: 'shop', guid: GUID }, state })
        );
      }
    );

    it('keeps the registration of a create that succeeded', async () => {
      const { deps, handler, repoRefForGuid } = rebuild('shop');
      await observeTerminalPoll(UNKNOWN_JOB, { state: 'succeeded', exitCode: 0, ...lost }, deps);
      expect(handler).not.toHaveBeenCalled();
      expect(repoRefForGuid).not.toHaveBeenCalled();
    });

    it('leaves a failed job of any other function alone', async () => {
      const { deps, handler } = rebuild('shop');
      await observeTerminalPoll(
        UNKNOWN_JOB,
        { state: 'failed', exitCode: 1, function: 'repository_up', repoGuid: GUID },
        deps
      );
      expect(handler).not.toHaveBeenCalled();
    });

    it('does nothing when the config holds no repository with that GUID', async () => {
      const { deps, handler } = rebuild(undefined);
      await observeTerminalPoll(UNKNOWN_JOB, { state: 'failed', exitCode: 1, ...lost }, deps);
      expect(handler).not.toHaveBeenCalled();
    });

    it('does not rebuild when the executor still holds the ticket', async () => {
      const { deps, handler } = rebuild('shop');
      await observeTerminalPoll(JOB, { state: 'failed', exitCode: 1, ...lost }, deps);
      expect(handler).not.toHaveBeenCalled();
    });
  });
});
