/**
 * Executor selection.
 *
 * Every machine-plane command resolves its executor here instead of importing
 * `localExecutorService` directly. The seam earns its keep twice over:
 *
 *   - It is where renet events are teed into an in-flight dispatch, so a command
 *     streams its progress to a console without knowing that anything is
 *     listening (event-tap.ts).
 *   - It is where the executor a dispatch pinned on the request context wins over
 *     the process default, which is how the serve layer drives a command body it
 *     does not control, and how a test drives one without touching a machine.
 *
 * What is NOT here any more: proxy routing. `--proxy` used to swap in a remote
 * executor at this seam, which was too deep to work. A command's action body does
 * config work on the way here (reading the repository, allocating a network id),
 * and a proxy client holds no config, so it never survived the trip. Proxying now
 * intercepts the whole COMMAND, before any action runs (proxy-command.ts), and
 * this file is once again about one thing: which executor runs the work.
 */

import { currentRequestContext } from '../core/request-context.js';
import { createDaemonExecutor } from './daemon/client.js';
import { requestExecutor, tapExecutor } from './event-tap.js';
import { localExecutorService } from './local-executor.js';
import type { Executor } from './types.js';

/**
 * The process default outside a dispatch: the same-host executor daemon, backed
 * by the direct local executor. The daemon amortises SSH/provision/cache cold
 * costs across consecutive `rdc` runs and falls back to the direct executor on
 * anything (no daemon, wrong platform, non-serializable options, a served
 * dispatch).
 *
 * Built lazily on first use, not at module load. `getExecutor` already read
 * `localExecutorService` lazily; constructing the wrapper here at module-init
 * would instead read it EAGERLY, and this module sits in an import cycle where
 * `localExecutorService` is not yet initialised at that moment — capturing
 * `undefined` as the fallback. One instance, since it holds no per-call state.
 */
let daemonBackedExecutor: Executor | undefined;
function getDaemonBackedExecutor(): Executor {
  daemonBackedExecutor ??= createDaemonExecutor(localExecutorService);
  return daemonBackedExecutor;
}

// The factory is the entry point to the executor layer, so callers get the
// seam's types from here too rather than reaching into an implementation.
export type { ExecuteResult, Executor, RenetEvent } from './types.js';

/**
 * Process-global set by `--background` / `-b` in the root preAction hook.
 *
 * A process global, not a threaded parameter, because there are ~35 hand-rolled
 * execute() call sites and threading a flag through all of them (and every
 * command body between the hook and the seam) is exactly the churn the executor
 * seam exists to avoid. The decorator below reads it once, at the seam.
 */
let backgroundRequested = false;

/** Called by the root preAction hook when `--background` is present. */
export function setBackgroundRequested(value: boolean): void {
  backgroundRequested = value;
}

/** Whether this invocation asked to fire-and-forget its machine work. */
export function isBackgroundRequested(): boolean {
  return backgroundRequested;
}

/**
 * Turn a `--background` invocation's machine work into a fire-and-forget
 * detached job: start it and return the instant it starts, leaving it running.
 *
 * Two guards keep this from misfiring. It only acts when the global is set, so
 * an ordinary run is untouched. And it is a NO-OP inside a serve request context
 * (`currentRequestContext()` present): the process global would otherwise leak
 * across concurrent in-flight requests, and inside a dispatch the dispatch owns
 * the detach decision (via `deps.detach`), not a client's flag.
 */
export function backgroundDecorator(inner: Executor): Executor {
  if (!backgroundRequested || currentRequestContext()) return inner;
  return {
    execute(options) {
      return inner.execute({ ...options, detached: true, follow: false });
    },
  };
}

/**
 * The executor for the current invocation.
 *
 * An in-process dispatch (the executor serving a command) pins its own executor
 * on the request context, so that wins. Outside a dispatch there is no context
 * and this is the daemon-backed executor, which transparently falls back to the
 * local executor whenever the daemon is unavailable or the work is not
 * daemon-eligible — so the effective behaviour on a laptop is unchanged.
 * `--background` composes over whichever it is, and is inert inside a dispatch.
 */
export function getExecutor(): Executor {
  return tapExecutor(backgroundDecorator(requestExecutor() ?? getDaemonBackedExecutor()));
}
