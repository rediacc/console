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
import type { RdcConfig } from '@rediacc/shared/config-schema';
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
  /**
   * Everything the command wrote to stdout. A Uint8Array chunk is raw bytes
   * (`repo cat` of a binary file), which must reach the client unchanged.
   */
  stdout: (string | Uint8Array)[];
  /** Everything the command wrote to stderr (info, warnings, errors). */
  stderr: string[];
  /**
   * The exit status the command asked for without exiting, the request's
   * counterpart of `process.exitCode`. Set through setExitCode(); the dispatch
   * reports it as the request's exit code.
   */
  exitCode?: number;
  /**
   * Renet events, teed as they stream so the route can forward them live.
   *
   * The optional second argument is the event's 1-based spool-line ordinal,
   * present only on a detached job's replayed stream (where the serve route
   * forwards it so a re-attaching client can dedupe). A synchronous stream omits
   * it, exactly as ExecuteOptions.onEvent does.
   */
  onEvent?: (event: RenetEvent, line?: number) => void;
  /**
   * The executor this request's commands must use, overriding the process
   * default. The serve layer injects the one from its deps, which is how the
   * loopback harness drives a real command body with a fake executor.
   */
  executor?: Executor;
  /**
   * The config this request's commands run against, overriding the disk.
   *
   * Set by the container tier, whose config exists only as the plaintext it
   * decrypted for this session: configFileStorage and configService serve it in
   * place of any file while the dispatch runs, so machine and repo lookups see
   * the decrypted config rather than an empty container disk. Absent on a
   * daemon, whose enrolled config on disk is the real one.
   */
  config?: RequestConfigScope;
}

/**
 * A config held for one request. Writes land here, in memory, and are never
 * persisted: the container has no config file to write, and the remote store
 * is not written back through the executor.
 */
export interface RequestConfigScope {
  /** The current plaintext config. Replaced (not mutated) by each write. */
  config: RdcConfig;
  /** configService's memoized resource view for THIS config, per request. */
  resourceState?: unknown;
  /** Version-bumping (spec) writes the command made; they die with the request. */
  specWrites: number;
}

/** A fresh request-scoped config holder around `config`. */
export function createRequestConfigScope(config: RdcConfig): RequestConfigScope {
  return { config, specWrites: 0 };
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

/** The request-scoped config in force, or undefined on a laptop or a daemon. */
export function currentRequestConfig(): RequestConfigScope | undefined {
  return storage.getStore()?.config;
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

/**
 * Raw stdout, or this request's buffer. For callers that bypass outputService.
 *
 * Bytes are kept as bytes: a Uint8Array chunk reaches a proxy client exactly as
 * written, however little of it is valid UTF-8.
 */
export function writeStdout(chunk: string | Uint8Array): void {
  const context = storage.getStore();
  if (context) context.stdout.push(chunk);
  else process.stdout.write(chunk);
}

/**
 * One streaming decoder per request, so a multi-byte character split across two
 * byte chunks decodes once, whole, instead of as two replacement characters.
 */
const stderrDecoders = new WeakMap<CommandRequestContext, TextDecoder>();

/** This request's streaming stderr decoder, created on first use. */
function stderrDecoderFor(context: CommandRequestContext): TextDecoder {
  let decoder = stderrDecoders.get(context);
  if (!decoder) {
    decoder = new TextDecoder('utf-8');
    stderrDecoders.set(context, decoder);
  }
  return decoder;
}

/** Append one stderr write to a request's buffer, text and bytes kept in order. */
function bufferStderr(context: CommandRequestContext, chunk: string | Uint8Array): void {
  if (typeof chunk === 'string') {
    // A text write ends any pending byte sequence first, keeping the order.
    const pending = stderrDecoders.get(context)?.decode() ?? '';
    if (pending) context.stderr.push(pending);
    context.stderr.push(chunk);
    return;
  }
  const text = stderrDecoderFor(context).decode(chunk, { stream: true });
  if (text) context.stderr.push(text);
}

/**
 * Raw stderr, or this request's buffer. A byte chunk (a subprocess's raw
 * output) is decoded as UTF-8 inside a dispatch, since stderr travels as text.
 */
export function writeStderr(chunk: string | Uint8Array): void {
  const context = storage.getStore();
  if (context) bufferStderr(context, chunk);
  else process.stderr.write(chunk);
}

/**
 * Set the exit status without exiting: `process.exitCode` on a laptop, this
 * request's exit code inside a dispatch.
 *
 * Setting process.exitCode inside the executor would be lost to the client (the
 * request still reports exit 0) and would leak into the executor's own exit.
 */
export function setExitCode(code: number): void {
  const context = storage.getStore();
  if (context) context.exitCode = code;
  else process.exitCode = code;
}

/**
 * Join a request's stdout chunks for the response.
 *
 * All-text output keeps its historic line join and travels as `text`. Once any
 * chunk is raw bytes the output is binary: every chunk is concatenated exactly
 * as a terminal would have received it (text as UTF-8, no separator added) and
 * travels as `bytes`, so nothing is re-encoded on the way to the client.
 */
export function joinStdout(chunks: readonly (string | Uint8Array)[]): {
  text: string;
  bytes?: Uint8Array;
} {
  if (chunks.every((chunk) => typeof chunk === 'string')) {
    return { text: (chunks as string[]).join('\n') };
  }
  const bytes = Buffer.concat(
    chunks.map((chunk) => (typeof chunk === 'string' ? Buffer.from(chunk, 'utf8') : chunk))
  );
  return { text: '', bytes: new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength) };
}
