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

import { requestExecutor, tapExecutor } from './event-tap.js';
import { localExecutorService } from './local-executor.js';
import type { Executor } from './types.js';

// The factory is the entry point to the executor layer, so callers get the
// seam's types from here too rather than reaching into an implementation.
export type { ExecuteResult, Executor, RenetEvent } from './types.js';

/**
 * The executor for the current invocation.
 *
 * An in-process dispatch (the executor serving a command) pins its own executor
 * on the request context, so that wins. Outside a dispatch there is no context
 * and this is the local executor, which is the only one there has ever been on a
 * laptop.
 */
export function getExecutor(): Executor {
  return tapExecutor(requestExecutor() ?? localExecutorService);
}
