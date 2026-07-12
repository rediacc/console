/**
 * The event tap: how a dispatched command's renet events reach the caller.
 *
 * A command sets `onEvent` itself, deep inside its own action body, to draw its
 * spinners and timeline. The executor cannot inject one from the outside without
 * every command knowing it is being served over HTTP. So instead of injecting,
 * this TEES: the executor seam wraps whatever executor a command resolves and
 * copies every event into the request context on its way past.
 *
 * The tap sits at the seam (getExecutor) rather than inside LocalExecutorService
 * deliberately. Every execute() in the CLI resolves through getExecutor, so the
 * seam catches all of them; and because it is implementation-blind, the loopback
 * harness's fake executor feeds the tap through the very same code path that
 * production uses. A tap buried in the local executor would be bypassed by any
 * injected executor, so the test would prove nothing about the production path.
 *
 * Dispatch also forces events on. A CLI run does not ask for eventsMode (it
 * renders steps by scraping stdout), but a console has no terminal to scrape:
 * the event stream IS its rendering. Capture and quiet spinners come with it,
 * since neither the container's stdout nor a spinner has any audience here.
 */

import { currentRequestContext } from '../core/request-context.js';
import type { ExecuteOptions, ExecuteResult, Executor } from './types.js';

/**
 * Wrap an executor so its events tee into the in-flight request.
 *
 * Returns `inner` untouched when no dispatch is in flight, so a CLI invocation
 * keeps the exact executor it always had.
 */
export function tapExecutor(inner: Executor): Executor {
  const context = currentRequestContext();
  if (!context?.onEvent) return inner;
  const emit = context.onEvent;

  return {
    execute(options: ExecuteOptions): Promise<ExecuteResult> {
      return inner.execute({
        ...options,
        eventsMode: true,
        captureOutput: true,
        quietSpinners: true,
        onEvent: (event) => {
          // The command's own handler still runs: it is what builds the
          // timeline that ends up in the result. The tap is additive.
          options.onEvent?.(event);
          emit(event);
        },
      });
    },
  };
}

/**
 * The executor this request must use, when the serve layer injected one.
 *
 * Production injects the same LocalExecutorService the CLI would have resolved,
 * so this changes nothing; the loopback harness injects a fake, which is how a
 * real command body can be driven without touching a machine.
 */
export function requestExecutor(): Executor | undefined {
  return currentRequestContext()?.executor;
}
