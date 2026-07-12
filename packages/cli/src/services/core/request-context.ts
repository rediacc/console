/**
 * The per-request context for in-process command dispatch.
 *
 * The executor runs commands by driving the real Commander tree in the same
 * process (services/serve/command-dispatch.ts), which is what keeps the warm SSH
 * pool and the decrypted config across commands. The CLI, though, was written for
 * exactly one command per process: it prints to stdout, records "the" command
 * name on a singleton, and ends a fatal error with process.exit(). None of that
 * survives contact with a server that runs many tenants' commands at once.
 *
 * So a dispatch runs inside an AsyncLocalStorage context, and the three
 * process-global assumptions are redirected into it:
 *
 *   1. OUTPUT. outputService writes into this context's buffers instead of the
 *      terminal, and its per-command state (command name, warnings, timings)
 *      lives here rather than on the singleton. Two commands in flight cannot
 *      interleave their output or overwrite each other's envelope.
 *   2. EVENTS. Renet events are teed here as they stream, so the route can
 *      forward them without every command having to learn about the executor.
 *   3. EXIT. process.exit() would kill the executor and every OTHER tenant's
 *      in-flight command. Inside a context, an exit becomes a thrown
 *      DispatchExit that unwinds this request only.
 *
 * AsyncLocalStorage is what makes this per-REQUEST rather than per-process: the
 * context follows the command's own async calls, however deep, and two
 * concurrent dispatches never see each other's. A module-global buffer would
 * interleave them, which is precisely the bug this exists to prevent.
 *
 * Outside a context (the CLI on a laptop) every one of these paths is unchanged.
 */

import { AsyncLocalStorage } from 'node:async_hooks';
import type { Executor, RenetEvent } from '../executor/types.js';

/**
 * Per-command output state.
 *
 * Held here rather than on the OutputService singleton so concurrent commands do
 * not overwrite each other's command name, warnings or timings, all of which end
 * up in the JSON envelope.
 */
export interface OutputState {
  quiet: boolean;
  fields: string[] | null;
  commandName: string | null;
  startTime: number | null;
  warnings: string[];
  operationDurationMs: number | null;
  timelineRendered: boolean;
}

export function createOutputState(): OutputState {
  return {
    quiet: false,
    fields: null,
    commandName: null,
    startTime: null,
    warnings: [],
    operationDurationMs: null,
    timelineRendered: false,
  };
}

export interface CommandRequestContext {
  /** Per-command output state, isolated from every other in-flight command. */
  output: OutputState;
  /** Everything the command wrote to stdout. */
  stdout: string[];
  /** Everything the command wrote to stderr (info, warnings, errors). */
  stderr: string[];
  /** Renet events, teed as they stream so the route can forward them live. */
  onEvent?: (event: RenetEvent) => void;
  /**
   * The executor this request's commands must use, overriding the process
   * default. The serve layer injects the one from its deps, which is how the
   * loopback harness drives a real command body with a fake executor.
   */
  executor?: Executor;
}

/**
 * Raised in place of process.exit() when a command exits inside a dispatch.
 *
 * A CLI process exits; a request unwinds. Carrying the code means the route can
 * still report the exit status the command intended.
 */
export class DispatchExit extends Error {
  constructor(readonly code: number) {
    super(`The command exited with code ${code}.`);
    this.name = 'DispatchExit';
  }
}

const storage = new AsyncLocalStorage<CommandRequestContext>();

/** The context of the in-flight dispatch, or undefined when running as a CLI. */
export function currentRequestContext(): CommandRequestContext | undefined {
  return storage.getStore();
}

/** Run `fn` with `context` bound to it and to everything it awaits. */
export function runInRequestContext<T>(
  context: CommandRequestContext,
  fn: () => Promise<T>
): Promise<T> {
  return storage.run(context, fn);
}

/**
 * End the process, or, inside a dispatch, end only this request.
 *
 * Every reachable process.exit() in the command path calls this instead. On a
 * laptop it exits exactly as before; in the executor it throws, so one tenant's
 * failed command cannot take down the process that is serving everyone else.
 */
export function exitProcess(code: number): never {
  if (storage.getStore()) {
    throw new DispatchExit(code);
  }
  process.exit(code);
}

/** Raw stdout, or this request's buffer. For callers that bypass outputService. */
export function writeStdout(text: string): void {
  const context = storage.getStore();
  if (context) context.stdout.push(text);
  else process.stdout.write(text);
}

/** Raw stderr, or this request's buffer. */
export function writeStderr(text: string): void {
  const context = storage.getStore();
  if (context) context.stderr.push(text);
  else process.stderr.write(text);
}
