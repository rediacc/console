/**
 * Executor background tasks (AX6, D5): a client disconnect leaves the task running, a destructive
 * proposal pauses it until an approval, the third task is refused, and the session's end fails it.
 */

import type { AiEvent } from '@rediacc/shared/cli-contract/wire';
import { describe, expect, it } from 'vitest';
import {
  AI_TASK_LIMIT,
  BackgroundTasks,
  MAX_TASKS_PER_USER,
  SESSION_EXPIRED_REASON,
  TASK_PATH_KEY,
  type TaskEnd,
  type TaskStart,
  type TaskStep,
} from '../background-task.js';

const APPROVAL: AiEvent = {
  type: 'approval_required',
  toolCallId: 'call-1',
  name: 'repo_down',
  input: {},
  approvalToken: 'tok',
  command: { pathKey: 'repo down', params: {}, positionals: {} },
  risk: 'destructive',
  reason: 'destructive',
} as AiEvent;

interface Harness {
  tasks: BackgroundTasks;
  ended: TaskEnd[];
  /** How many run records were opened: a refused start opens none. */
  begun: { count: number };
  /** The commands the task ran: the held command runs only in a resumed step. */
  ran: string[];
  alive: { value: boolean };
  start: (
    taskId: string,
    step?: TaskStart['step'],
    owner?: string
  ) => ReturnType<BackgroundTasks['start']>;
}

function harness(): Harness {
  const tasks = new BackgroundTasks();
  const ended: Harness['ended'] = [];
  const begun = { count: 0 };
  const ran: string[] = [];
  const alive = { value: true };
  const proposing = (input: TaskStep): Promise<void> => {
    if (input.resumed) ran.push('repo down');
    else input.emit(APPROVAL);
    return Promise.resolve();
  };
  return {
    tasks,
    ended,
    begun,
    ran,
    alive,
    start: (taskId, step = proposing, owner = 'org\u0000alice') =>
      tasks.start({
        owner,
        taskId,
        step,
        beginRun: () => {
          begun.count += 1;
          return {
            end: (outcome) => {
              ended.push(outcome);
              return Promise.resolve();
            },
          };
        },
        sessionAlive: () => alive.value,
      }),
  };
}

const NEVER = (): Promise<void> => new Promise(() => undefined);

describe('background tasks', () => {
  it('is recorded as an ai.task run', () => {
    expect(TASK_PATH_KEY).toBe('ai.task');
  });

  it('keeps running when the client that started it disconnects', async () => {
    const h = harness();
    const request = new AbortController();
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    let sawAbort = false;
    h.start('t1', async ({ signal }) => {
      // The step is handed its own signal, not the request's.
      request.signal.addEventListener('abort', () => {
        sawAbort = signal.aborted;
      });
      await gate;
    });
    request.abort();
    expect(h.tasks.get('org\u0000alice', 't1')?.state).toBe('running');
    release();
    await h.tasks.settled('t1');
    expect(sawAbort).toBe(false);
    expect(h.tasks.get('org\u0000alice', 't1')?.state).toBe('succeeded');
    expect(h.ended).toEqual([{ state: 'succeeded' }]);
  });

  it('pauses on a destructive proposal and runs the command only once approved', async () => {
    const h = harness();
    h.start('t1');
    await h.tasks.settled('t1');
    expect(h.tasks.get('org\u0000alice', 't1')?.state).toBe('needs_approval');
    expect(h.ran).toEqual([]);
    expect(h.ended).toEqual([]);
    // Control: another user's approval does nothing, and only the owner's approval resumes the task.
    expect(h.tasks.approve('org\u0000mallory', 't1')).toBe(false);
    expect(h.ran).toEqual([]);
    expect(h.tasks.approve('org\u0000alice', 't1')).toBe(true);
    await h.tasks.settled('t1');
    expect(h.ran).toEqual(['repo down']);
    expect(h.tasks.get('org\u0000alice', 't1')?.state).toBe('succeeded');
  });

  it('ends a rejected task cancelled without running the held command', async () => {
    const h = harness();
    h.start('t1');
    await h.tasks.settled('t1');
    expect(await h.tasks.reject('org\u0000alice', 't1')).toBe(true);
    expect(h.ran).toEqual([]);
    expect(h.ended).toEqual([{ state: 'cancelled' }]);
    expect(h.tasks.approve('org\u0000alice', 't1')).toBe(false);
  });

  it('refuses a third task, counting a paused one, and frees the slot when one ends', async () => {
    const h = harness();
    expect(MAX_TASKS_PER_USER).toBe(2);
    expect(h.start('t1', NEVER).ok).toBe(true);
    expect(h.start('t2').ok).toBe(true);
    await h.tasks.settled('t2');
    const opened = h.begun.count;
    const third = h.start('t3', NEVER);
    expect(third).toMatchObject({ ok: false, code: AI_TASK_LIMIT });
    // A refused start opens no run record (bac5934c.1): the run index would otherwise hold a run nothing ends.
    expect(h.begun.count).toBe(opened);
    expect(h.start('t1', NEVER)).toMatchObject({ ok: false, code: 'AI_TASK_EXISTS' });
    expect(h.begun.count).toBe(opened);
    // Control: the cap is per user.
    expect(h.start('t4', NEVER, 'org\u0000bob').ok).toBe(true);
    await h.tasks.cancel('org\u0000alice', 't1');
    expect(h.start('t3', NEVER).ok).toBe(true);
  });

  it('ends a task whose session key expired as failed with that reason', async () => {
    const h = harness();
    h.start('t1');
    await h.tasks.settled('t1');
    h.alive.value = false;
    expect(h.tasks.get('org\u0000alice', 't1')).toMatchObject({
      state: 'failed',
      reason: SESSION_EXPIRED_REASON,
    });
    expect(h.tasks.approve('org\u0000alice', 't1')).toBe(false);
    expect(h.ran).toEqual([]);
    expect(h.ended).toEqual([{ state: 'failed', errorCode: 'AI_TASK_FAILED' }]);
  });

  it('ends a task whose step throws or reports an error event as failed', async () => {
    const h = harness();
    h.start('t1', () => Promise.reject(new Error('boom')));
    h.start('t2', ({ emit }) => {
      emit({ type: 'error', message: 'provider down' });
      return Promise.resolve();
    });
    await h.tasks.settled('t1');
    await h.tasks.settled('t2');
    expect(h.tasks.get('org\u0000alice', 't1')).toMatchObject({ state: 'failed', reason: 'boom' });
    expect(h.tasks.get('org\u0000alice', 't2')).toMatchObject({
      state: 'failed',
      reason: 'provider down',
    });
  });

  it('keeps the events of a task for its result card, for the owner only', async () => {
    const h = harness();
    h.start('t1');
    await h.tasks.settled('t1');
    expect(h.tasks.eventsOf('org\u0000alice', 't1')).toEqual([APPROVAL]);
    expect(h.tasks.eventsOf('org\u0000mallory', 't1')).toBeUndefined();
    expect(h.tasks.list('org\u0000mallory')).toEqual([]);
  });
});
