/**
 * Tests for the follow loop's detach semantics.
 *
 * The one property that matters here: interrupting a follow DETACHES, it never
 * cancels. A served follow hangs off the request's AbortSignal, so a client
 * disconnect must leave the job running on the machine and issue no `job cancel`.
 */

import { describe, expect, it, vi } from 'vitest';
import { createOutputState, runInRequestContext } from '../../core/request-context.js';
import { JobLogCursor } from '../job-client.js';
import { FollowLostError, followJobLogs, renderJobEvent } from '../job-remote.js';
import type { RenetEvent } from '../types.js';

const JOB_ID = 'j18c1994eaa33d30d-3d9813b2';

describe('followJobLogs abort (detach, not cancel)', () => {
  it('resolves interrupted when the signal aborts mid-stream, without cancelling', async () => {
    const controller = new AbortController();
    const rendered: RenetEvent[] = [];
    const cursor = new JobLogCursor();

    const execStreaming = vi.fn((_cmd: string, handlers: { onStdout: (data: Buffer) => void }) => {
      // Deliver one complete event, then abort. A live follow never returns on
      // its own; only the abort ends it, so this promise stays pending.
      handlers.onStdout(Buffer.from('{"type":"output","msg":"hello"}\n'));
      controller.abort();
      return new Promise<number>(() => {});
    });
    const sftp = { execStreaming };
    const lease = { sftp, ensure: () => Promise.resolve(sftp), release: () => {} };

    const interrupted = await followJobLogs(
      lease as never,
      '/usr/bin/renet',
      JOB_ID,
      { onEvent: (event) => rendered.push(event), signal: controller.signal },
      cursor
    );

    expect(interrupted).toBe(true);
    // The event that arrived before the abort was still delivered and counted.
    expect(rendered).toHaveLength(1);
    expect(cursor.sinceLine).toBe(1);
    // The only command run was `job logs`; nothing cancelled the job.
    expect(String(execStreaming.mock.calls[0][0])).toContain('job logs');
    expect(execStreaming.mock.calls.every((call) => !String(call[0]).includes('job cancel'))).toBe(
      true
    );
  });

  it('detaches immediately when the signal is already aborted', async () => {
    const cursor = new JobLogCursor();
    const execStreaming = vi.fn(() => new Promise<number>(() => {}));
    const sftp = { execStreaming };
    const lease = { sftp, ensure: () => Promise.resolve(sftp), release: () => {} };

    const interrupted = await followJobLogs(
      lease as never,
      '/usr/bin/renet',
      JOB_ID,
      { onEvent: () => {}, signal: AbortSignal.abort() },
      cursor
    );

    expect(interrupted).toBe(true);
  });
});

describe('followJobLogs reconnect budget (Design 2, section 16)', () => {
  /** A fake clock: every pause advances it. */
  function clock() {
    let now = 0;
    return {
      now: () => now,
      sleep: (ms: number) => {
        now += ms;
        return Promise.resolve();
      },
    };
  }

  it('keeps reconnecting well past five drops while inside the 2-minute budget, then finishes', async () => {
    let calls = 0;
    const execStreaming = vi.fn((_cmd: string, handlers: { onStdout: (data: Buffer) => void }) => {
      calls += 1;
      // Twelve drops in a row (the old ceiling was five), then the tail delivers and ends.
      if (calls <= 12) return Promise.reject(new Error('channel closed'));
      handlers.onStdout(Buffer.from('{"type":"output","msg":"done"}\n'));
      return Promise.resolve(0);
    });
    const sftp = { execStreaming };
    const lease = { sftp, ensure: () => Promise.resolve(sftp), release: () => {} };
    const cursor = new JobLogCursor(4);

    const interrupted = await followJobLogs(
      lease as never,
      '/usr/bin/renet',
      JOB_ID,
      { onEvent: () => {}, reconnect: clock() },
      cursor
    );

    expect(interrupted).toBe(false);
    expect(calls).toBe(13);
    // Every reconnect resumed from the last complete line.
    expect(String(execStreaming.mock.calls[12][0])).toContain('--since-line 4');
    expect(cursor.sinceLine).toBe(5);
  });

  it('gives up with FollowLostError, carrying the last line, once the transport stays gone past the budget', async () => {
    const execStreaming = vi.fn(() => Promise.reject(new Error('channel closed')));
    const sftp = { execStreaming };
    const lease = { sftp, ensure: () => Promise.resolve(sftp), release: () => {} };

    const error = await followJobLogs(
      lease as never,
      '/usr/bin/renet',
      JOB_ID,
      { onEvent: () => {}, reconnect: { ...clock(), budgetMs: 120_000 } },
      new JobLogCursor(7)
    ).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(FollowLostError);
    expect((error as FollowLostError).sinceLine).toBe(7);
    // 120 s at a 5 s capped backoff is well over five attempts.
    expect(execStreaming.mock.calls.length).toBeGreaterThan(20);
  });
});

describe('renderJobEvent request-context routing', () => {
  it('writes into the request buffer inside a dispatch, not the container stdout', async () => {
    const context = { output: createOutputState(), stdout: [] as string[], stderr: [] as string[] };

    await runInRequestContext(context, () => {
      renderJobEvent({ type: 'output', msg: 'hello' });
      renderJobEvent({ type: 'log', level: 'error', msg: 'boom' });
      return Promise.resolve();
    });

    expect(context.stdout.join('')).toContain('hello');
    expect(context.stderr.join('')).toContain('boom');
  });
});
