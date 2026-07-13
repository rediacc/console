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
import { followJobLogs, renderJobEvent } from '../job-remote.js';
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
