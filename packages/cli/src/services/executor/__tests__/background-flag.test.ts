/**
 * The `--background` decorator (B9 of the ref/detach work).
 *
 * `--background` turns a local command's machine work into a fire-and-forget
 * detached job by composing a decorator at the executor seam. Two properties
 * matter and are pinned here: it forwards `{ detached: true, follow: false }`
 * ONLY when the process global is set, and it is a strict NO-OP inside a serve
 * request context so the global can never leak across concurrent requests.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { createOutputState, runInRequestContext } from '../../core/request-context.js';
import {
  backgroundDecorator,
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

afterEach(() => setBackgroundRequested(false));

describe('background flag', () => {
  it('defaults off, and the setter flips it', () => {
    expect(isBackgroundRequested()).toBe(false);
    setBackgroundRequested(true);
    expect(isBackgroundRequested()).toBe(true);
  });

  it('forwards detached + no-follow when the global is set, outside a request', async () => {
    const { calls, executor } = recordingExecutor();
    setBackgroundRequested(true);

    await backgroundDecorator(executor).execute({
      functionName: 'repository_up',
      machineName: 'm',
    });

    expect(calls).toHaveLength(1);
    expect(calls[0].detached).toBe(true);
    expect(calls[0].follow).toBe(false);
  });

  it('is a no-op when the global is not set', async () => {
    const { calls, executor } = recordingExecutor();
    // Not set: the decorator returns the inner executor untouched.
    expect(backgroundDecorator(executor)).toBe(executor);

    await backgroundDecorator(executor).execute({
      functionName: 'repository_up',
      machineName: 'm',
    });
    expect(calls[0].detached).toBeUndefined();
    expect(calls[0].follow).toBeUndefined();
  });

  it('NEVER detaches inside a serve request context, even with the global set', async () => {
    const { calls, executor } = recordingExecutor();
    setBackgroundRequested(true);

    // A dispatch owns the detach decision; a client's process global must not
    // leak into it, or one request would detach another's work.
    await runInRequestContext({ output: createOutputState(), stdout: [], stderr: [] }, async () => {
      expect(backgroundDecorator(executor)).toBe(executor);
      await backgroundDecorator(executor).execute({
        functionName: 'repository_up',
        machineName: 'm',
      });
    });

    expect(calls[0].detached).toBeUndefined();
    expect(calls[0].follow).toBeUndefined();
  });
});
