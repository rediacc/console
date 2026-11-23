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
   * The client asked for `--background` (CommandRequest.background): every
   * machine job of this request starts with a zero attach window. Read per
   * request, never from the process global, which concurrent requests share.
   */
  background?: boolean;
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
 * Where a request-scoped config's writes are saved: the config store the
 * executor pulled the config from (services/serve/config-writeback.ts).
 *
 * `write` applies `edit` to the newest copy of the stored config, pushes the
 * result with compare-and-swap, replays `edit` on a fresh pull after a version
 * conflict, and resolves to the document the store now holds (its `version` the
 * store's). It throws when the change could not be saved, so a command fails
 * before the host job its write precedes.
 */
export interface ConfigWriteback {
  write(edit: (config: RdcConfig) => RdcConfig): Promise<RdcConfig>;
}

/**
 * A config held for one request.
 *
 * With a writeback (the container tier's session config), every write that
 * changes the stored document is pushed through it: a spec write and a state
 * write alike, since `state` syncs too and a network ID recorded only in memory
 * would be lost with the request. A cache write (`updateCache`) stays here.
 *
 * Without one, a state write applies here, in memory, for the rest of the
 * request, and a version-bumping (spec) write is refused with
 * ConfigWriteUnavailableError (services/core/config-write-errors.ts): a change
 * that lives only in this request would vanish with it while the host side
 * effect it registered (a volume, a fork) stayed. The write precedes the
 * command's host job, so the refusal ends the command before any machine is
 * touched (agent/plans/PLAN-rmcp-writeback.md D6).
 */
export interface RequestConfigScope {
  /** The current plaintext config. Replaced (not mutated) by each write. */
  config: RdcConfig;
  /** configService's memoized resource view for THIS config, per request. */
  resourceState?: unknown;
  /** Where this config's writes are saved; absent when the config has no store to push to. */
  writeback?: ConfigWriteback;
  /**
   * The error code of a config write this scope refused or failed to save
   * (CONFIG_WRITE_UNAVAILABLE, CONFIG_CONFLICT, CONFIG_WRITE_FAILED). The command's
   * own error handling flattens the thrown error into an exit, so the dispatch
   * reads the code from here to put it on the served result.
   */
  writeFailure?: string;
}

/**
 * The writeback of each config a loader handed out, keyed by the very object.
 *
 * The container tier's loader binds the config it returns for a session to that
 * session's writeback (bindConfigWriteback), and every request scope built
 * around that object picks it up here: the command dispatch, the job routes and
 * the policy check all build their scope from the loader's config, so none of
 * them can run a write-capable command against a scope that silently drops it.
 * A WeakMap, so a config nobody references any more releases its writeback.
 */
const writebacks = new WeakMap<RdcConfig, ConfigWriteback>();

/** Make every request scope built around `config` save its writes through `writeback`. */
export function bindConfigWriteback(config: RdcConfig, writeback: ConfigWriteback): void {
  writebacks.set(config, writeback);
}

/** A fresh request-scoped config holder around `config`, with the writeback bound to it, if any. */
export function createRequestConfigScope(config: RdcConfig): RequestConfigScope {
  const writeback = writebacks.get(config);
  return writeback ? { config, writeback } : { config };
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

let stderrListener: ((text: string) => void) | undefined;

/**
 * Observe what the CLI writes to the terminal's stderr outside a dispatch (the
 * feedback ring's tail). One listener; undefined removes it. Every CLI stderr
 * write goes through writeStderr or outputService, which the proxy-safe output
 * gate enforces, so the listener sees the CLI's whole stderr without patching
 * the process stream.
 */
export function setStderrListener(listener: ((text: string) => void) | undefined): void {
  stderrListener = listener;
}

/** Hand one terminal stderr write to the listener. A listener failure never reaches the write. */
export function notifyStderr(chunk: string | Uint8Array): void {
  if (!stderrListener) return;
  try {
    stderrListener(typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString());
  } catch {
    // Observing stderr never interferes with the write itself.
  }
}

/**
 * Raw stderr, or this request's buffer. A byte chunk (a subprocess's raw
 * output) is decoded as UTF-8 inside a dispatch, since stderr travels as text.
 */
export function writeStderr(chunk: string | Uint8Array): void {
  const context = storage.getStore();
  if (context) {
    bufferStderr(context, chunk);
    return;
  }
  notifyStderr(chunk);
  process.stderr.write(chunk);
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
