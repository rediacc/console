/**
 * The attach decorator at the executor seam (agent/plans/PLAN-detached-jobs.md
 * sections 15 and 17): the entry point, never the verb, sets each call's attach
 * window, and the invoking process mints its request id.
 *
 *   - direct terminal run: unlimited (no window);
 *   - `--background`: 0, the ticket at once;
 *   - a served dispatch (proxy, web console) or an MCP child: JOB_ATTACH_WINDOW_MS;
 *   - the `--background` global never leaks into a served dispatch.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createOutputState, runInRequestContext } from '../../core/request-context.js';
import { JOB_ATTACH_WINDOW_MS, JOB_CLIENT_ENV, resetInvocationMinter } from '../../jobs/attach.js';
import {
  attachDecorator,
  isBackgroundRequested,
  setBackgroundRequested,
} from '../executor-factory.js';
import type { ExecuteOptions, ExecuteResult, Executor } from '../types.js';

/** An executor that records the options it was handed. */
function recordingExecutor(): { calls: ExecuteOptions[]; executor: Executor } {
  const calls: ExecuteOptions[] = [];
  return {
    calls,
    executor: {
      execute(options: ExecuteOptions): Promise<ExecuteResult> {
        calls.push(options);
        return Promise.resolve({ success: true, exitCode: 0, durationMs: 1 });
      },
    },
  };
}

const call = { functionName: 'repository_up', machineName: 'm' };

beforeEach(() => resetInvocationMinter('inv-1'));
afterEach(() => {
  setBackgroundRequested(false);
  delete process.env[JOB_CLIENT_ENV];
  resetInvocationMinter();
});

describe('attach decorator', () => {
  it('defaults the background flag off, and the setter flips it', () => {
    expect(isBackgroundRequested()).toBe(false);
    setBackgroundRequested(true);
    expect(isBackgroundRequested()).toBe(true);
  });

  it('leaves a direct terminal run attached for the whole job', async () => {
    const { calls, executor } = recordingExecutor();
    await attachDecorator(executor).execute(call);
    expect(calls[0].attachWindowMs).toBeUndefined();
  });

  it('gives --background a window of 0, outside a request', async () => {
    const { calls, executor } = recordingExecutor();
    setBackgroundRequested(true);
    await attachDecorator(executor).execute(call);
    expect(calls[0].attachWindowMs).toBe(0);
  });

  it('gives a served dispatch the proxy window, even with the --background global set', async () => {
    const { calls, executor } = recordingExecutor();
    setBackgroundRequested(true);
    // A dispatch's window is the proxy's; a client's process global must not leak into it, or one request would background another's work.
    await runInRequestContext({ output: createOutputState(), stdout: [], stderr: [] }, () =>
      attachDecorator(executor).execute(call)
    );
    expect(calls[0].attachWindowMs).toBe(JOB_ATTACH_WINDOW_MS);
  });

  it('gives an MCP child the MCP window', async () => {
    const { calls, executor } = recordingExecutor();
    process.env[JOB_CLIENT_ENV] = 'mcp';
    await attachDecorator(executor).execute(call);
    expect(calls[0].attachWindowMs).toBe(JOB_ATTACH_WINDOW_MS);
  });

  it('mints one request id per call from the invocation id, per machine', async () => {
    const { calls, executor } = recordingExecutor();
    const decorated = attachDecorator(executor);
    await decorated.execute(call);
    await decorated.execute(call);
    await decorated.execute({ ...call, machineName: 'other' });
    expect(calls.map((c) => c.requestId)).toEqual(['inv-1:m:1', 'inv-1:m:2', 'inv-1:other:1']);
  });

  it("keeps a caller's explicit window and request id", async () => {
    const { calls, executor } = recordingExecutor();
    setBackgroundRequested(true);
    await attachDecorator(executor).execute({ ...call, attachWindowMs: 5, requestId: 'r-1' });
    expect(calls[0]).toMatchObject({ attachWindowMs: 5, requestId: 'r-1' });
  });
});
