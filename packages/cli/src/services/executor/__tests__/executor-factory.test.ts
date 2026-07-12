/**
 * Executor selection tests.
 *
 * The factory decides which executor runs a command's machine work. It used to
 * also decide whether that work went over SSH from here or through a proxy; it
 * does not any more, because `--proxy` intercepts the whole COMMAND before an
 * action body ever runs (proxy-command.ts). What is left is the seam itself: the
 * local executor by default, an injected one when a dispatch pinned one, and the
 * event tap over both.
 */

import { describe, expect, it } from 'vitest';
import { createOutputState, runInRequestContext } from '../../core/request-context.js';
import { getExecutor } from '../executor-factory.js';
import { localExecutorService } from '../local-executor.js';
import type { ExecuteOptions, ExecuteResult, Executor, RenetEvent } from '../types.js';

function fakeExecutor(): { executor: Executor; calls: ExecuteOptions[] } {
  const calls: ExecuteOptions[] = [];
  return {
    calls,
    executor: {
      execute(options: ExecuteOptions): Promise<ExecuteResult> {
        calls.push(options);
        options.onEvent?.({ type: 'log', msg: 'from the executor' });
        return Promise.resolve({ success: true, exitCode: 0, durationMs: 1 });
      },
    },
  };
}

describe('executor factory', () => {
  it('is the local executor when nothing is dispatching', () => {
    expect(getExecutor()).toBe(localExecutorService);
  });

  it('prefers the executor a dispatch pinned on the request context', async () => {
    const { executor, calls } = fakeExecutor();

    await runInRequestContext(
      { output: createOutputState(), stdout: [], stderr: [], executor },
      async () => {
        await getExecutor().execute({ functionName: 'repository_status', machineName: 'm' });
      }
    );

    expect(calls).toHaveLength(1);
    expect(calls[0].functionName).toBe('repository_status');
  });

  it("tees renet events into the dispatch, on top of the command's own handler", async () => {
    const { executor, calls } = fakeExecutor();
    const tapped: RenetEvent[] = [];
    const commandsOwn: RenetEvent[] = [];

    await runInRequestContext(
      {
        output: createOutputState(),
        stdout: [],
        stderr: [],
        executor,
        onEvent: (event) => tapped.push(event),
      },
      async () => {
        await getExecutor().execute({
          functionName: 'repository_status',
          machineName: 'm',
          // The command's own handler is what draws its timeline. The tap is
          // additive, so it must not replace it.
          onEvent: (event) => commandsOwn.push(event),
        });
      }
    );

    expect(tapped.map((e) => e.msg)).toEqual(['from the executor']);
    expect(commandsOwn.map((e) => e.msg)).toEqual(['from the executor']);

    // A dispatch forces events on: a console has no terminal whose stdout it
    // could scrape for steps, so the event stream IS its rendering.
    expect(calls[0].eventsMode).toBe(true);
    expect(calls[0].captureOutput).toBe(true);
  });

  it('leaves an untapped call untouched: nothing rewritten', async () => {
    const { executor, calls } = fakeExecutor();

    await runInRequestContext(
      { output: createOutputState(), stdout: [], stderr: [], executor },
      async () => {
        await getExecutor().execute({ functionName: 'repository_status', machineName: 'm' });
      }
    );

    // Pinned but not tapped (no onEvent on the context): options pass through
    // verbatim rather than being rewritten into events mode.
    expect(calls).toHaveLength(1);
    expect(calls[0].eventsMode).toBeUndefined();
  });
});
