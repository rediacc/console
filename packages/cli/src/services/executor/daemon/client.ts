/**
 * The daemon-backed executor: a transparent front for localExecutorService that
 * routes an execute() through the same-host daemon when one is (or can be made)
 * available, and falls back to running it directly on ANY trouble.
 *
 * The contract is "never make a command worse". A connect refusal, a token or
 * identity mismatch, or a drop BEFORE the daemon began the work all fall back to
 * the direct path, so the daemon is a pure latency optimisation the operator
 * never has to think about. The one thing it must not do is re-run work that may
 * already have run: once the daemon sends `accepted` the command is in flight on
 * a machine, so a later failure is surfaced rather than silently retried (a
 * fallback there could fork/push/deploy twice). This is a deliberate, safer
 * reading of "fall back on mid-stream drop".
 */

import { randomUUID } from 'node:crypto';
import * as net from 'node:net';
import { debugEnabled } from '../../../utils/debug.js';
import { currentRequestContext } from '../../core/request-context.js';
import { renderJobEvent } from '../job-remote.js';
import type { ExecuteOptions, ExecuteResult, Executor, RenetEvent } from '../types.js';
import {
  daemonSocketPath,
  isDaemonPlatform,
  processIdentity,
  readToken,
  spawnDaemon as realSpawnDaemon,
  tokenPathFor,
  waitForSocket,
} from './lifecycle.js';
import {
  createFrameReader,
  encodeFrame,
  isDaemonSerializable,
  type ServerFrame,
  type StatusFrame,
  type StopFrame,
  toWireOptions,
} from './protocol.js';

/** Injectable seams so the client is testable against a fake server on a temp socket. */
export interface DaemonClientDeps {
  socketPath?: string;
  identity?: string;
  spawnDaemon?: () => void;
  /** How long to wait for a just-spawned daemon to accept a connection. */
  spawnWaitMs?: number;
  /**
   * Test-only: exercise the daemon path even under vitest. Production leaves this
   * unset, so the wrapper stays inert inside unit tests (see daemonEligible).
   * ONLY the daemon's own tests, which inject a fake server, set it.
   */
  allowUnderTest?: boolean;
}

/** How long to wait for a just-spawned daemon to accept a connection. */
const DEFAULT_SPAWN_WAIT_MS = 2000;

/** Raised for any pre-execution trouble; the caller falls back to the direct path. */
class DaemonUnavailable extends Error {}

/** Cap on withheld relay lines. A failing job's tail is what matters, not its head. */
/**
 * Send one event to the terminal, holding info-level logs for a possible replay.
 *
 * error/warning go out live because they explain a failure as it happens.
 * Everything quieter is buffered by `remember` and replayed only if the job
 * fails: those lines were 227-358 columns wide and wrapped into garbage in every
 * tutorial recording, but DROPPING them was tried and is worse - a renet child
 * exited 1 with every explanatory line at info level, and the failure became
 * unreadable. REDIACC_DEBUG restores the old firehose.
 *
 * Extracted from the frame switch rather than inlined: inline it pushed that
 * function past the cognitive-complexity gate.
 */
function routeLogEvent(event: RenetEvent, remember: (line: string) => void): void {
  if (event.type !== 'log' || !event.msg) {
    renderJobEvent(event);
    return;
  }
  if (event.level === 'error' || event.level === 'warning' || debugEnabled()) {
    process.stderr.write(`${event.msg}\n`);
    return;
  }
  remember(event.msg);
}

const DEFERRED_LOG_LIMIT = 200;

function debug(message: string): void {
  if (debugEnabled('daemon')) {
    process.stderr.write(`[executor-daemon] ${message}\n`);
  }
}

/**
 * Whether these options may be served by the daemon at all. Everything that
 * cannot be faithfully reproduced from a returned result plus streamed events
 * stays on the direct path: an interactive/PTY or client-side-streaming command
 * (passthroughOutput), a detached job (its own live tail), a served dispatch
 * (which pins its own executor), or a non-serializable option.
 *
 * It is also inert under vitest (`process.env.VITEST`): the CLI's unit tests mock
 * localExecutorService.execute and call getExecutor(), and a wrapper that probed
 * a socket, auto-spawned a real daemon process, and shifted call counts would
 * break dozens of unrelated tests. The daemon's own tests opt back in with
 * `allowUnderTest`, having injected a fake server. Operators use REDIACC_NO_DAEMON.
 */
function daemonEligible(options: ExecuteOptions, allowUnderTest: boolean): boolean {
  if (!allowUnderTest && process.env.VITEST) return false;
  return (
    isDaemonPlatform() &&
    process.env.REDIACC_NO_DAEMON !== '1' &&
    !currentRequestContext() &&
    !options.detached &&
    !options.passthroughOutput &&
    isDaemonSerializable(options)
  );
}

interface ResolvedDeps {
  socketPath: string;
  identity: string;
  spawn: () => void;
  spawnWaitMs: number;
  allowUnderTest: boolean;
}

/**
 * Redraw the CLI-side provision timeline the daemon could not show.
 *
 * "Config loaded / Connected / Renet provisioned / Machine verified" are NOT
 * renet events — the direct path draws them from its own spinners (timedStep),
 * which in the daemon write to a /dev/null stdout. They survive in
 * result.cliSteps, so we synthesize a step_done event per entry and route it
 * through the SAME renderer the detached-job and serve paths use (renderJobEvent
 * → getDoneLabel), reproducing the exact "✔ Config loaded (2ms)" lines. Warm
 * daemon runs make these near-zero, which is true.
 *
 * Gated exactly like the direct path's spinners: only when the caller drew no
 * onEvent of its own and did not ask for quiet. Not gated on captureOutput,
 * because the direct path shows these steps for captured (table) commands too.
 */
function renderCliSteps(options: ExecuteOptions, result: ExecuteResult): void {
  if (options.onEvent || options.quietSpinners) return;
  for (const step of result.cliSteps ?? []) {
    const event: RenetEvent = { type: 'step_done', name: step.name, duration_ms: step.duration_ms };
    renderJobEvent(event);
  }
}

/** Build the daemon-backed executor wrapping a direct fallback. */
export function createDaemonExecutor(fallback: Executor, deps: DaemonClientDeps = {}): Executor {
  const resolved: ResolvedDeps = {
    socketPath: deps.socketPath ?? daemonSocketPath(),
    identity: deps.identity ?? processIdentity(),
    spawn: deps.spawnDaemon ?? realSpawnDaemon,
    spawnWaitMs: deps.spawnWaitMs ?? DEFAULT_SPAWN_WAIT_MS,
    allowUnderTest: deps.allowUnderTest ?? false,
  };

  return {
    async execute(options: ExecuteOptions): Promise<ExecuteResult> {
      if (!daemonEligible(options, resolved.allowUnderTest)) return fallback.execute(options);
      try {
        return await runViaDaemon(options, resolved);
      } catch (error) {
        if (error instanceof DaemonUnavailable) {
          debug(`falling back to direct: ${error.message}`);
          return fallback.execute(options);
        }
        // Post-`accepted` failure: the work may already have started, so surface
        // it rather than re-running it directly.
        throw error;
      }
    },
  };
}

/** Connect to the running daemon, spawning one and waiting if none answers. */
async function connectOrSpawn(deps: ResolvedDeps): Promise<net.Socket> {
  const direct = await tryConnect(deps.socketPath);
  if (direct) return direct;
  deps.spawn();
  const spawned = await waitForSocket(deps.socketPath, deps.spawnWaitMs);
  if (spawned) return spawned;
  throw new DaemonUnavailable('no daemon after spawn');
}

function tryConnect(socketPath: string): Promise<net.Socket | null> {
  return new Promise((resolve) => {
    const socket = net.connect(socketPath);
    const onError = (): void => {
      socket.destroy();
      resolve(null);
    };
    socket.once('error', onError);
    socket.once('connect', () => {
      socket.removeListener('error', onError);
      resolve(socket);
    });
  });
}

/**
 * Run one execute over the socket. Resolves with the ExecuteResult, or throws:
 * DaemonUnavailable for any pre-`accepted` trouble (caller falls back), or a
 * plain Error for a failure after the daemon began the work (caller must not
 * retry).
 */
async function runViaDaemon(options: ExecuteOptions, deps: ResolvedDeps): Promise<ExecuteResult> {
  const socket = await connectOrSpawn(deps);
  const token = readToken(tokenPathFor(deps.socketPath)) ?? '';
  const id = randomUUID();

  return new Promise<ExecuteResult>((resolve, reject) => {
    let settled = false;
    let accepted = false;
    // Info-level relay lines are DEFERRED, not dropped. Printing them live put
    // 358-column logrus strings on screen (and into every tutorial recording);
    // dropping them outright is worse, and was tried: a renet child exited 1 and
    // every explanatory line was an info-level log event, so the failure became
    // unreadable. Buffering keeps both properties -- silent on success, complete
    // on failure. Bounded so a chatty job cannot grow it without limit.
    const deferredLogs: string[] = [];
    const rememberLog = (line: string): void => {
      deferredLogs.push(line);
      if (deferredLogs.length > DEFERRED_LOG_LIMIT) deferredLogs.shift();
    };
    const flushDeferredLogs = (): void => {
      for (const line of deferredLogs) process.stderr.write(`${line}\n`);
      deferredLogs.length = 0;
    };

    const finish = (fn: () => void): void => {
      if (settled) return;
      settled = true;
      socket.destroy();
      fn();
    };

    const read = createFrameReader<ServerFrame>((frame) => {
      switch (frame.type) {
        case 'helloOk':
          return;
        case 'stale':
          // The daemon runs a different build. Bring up a fresh one for the next
          // invocation, and fall back to direct for this one.
          deps.spawn();
          finish(() => reject(new DaemonUnavailable('stale daemon')));
          return;
        case 'accepted':
          accepted = true;
          return;
        case 'event':
          if (options.onEvent) options.onEvent(frame.event, frame.line);
          else if (!options.captureOutput) {
            // Parity with the direct path, which echoes renet's stderr live
            // (local-executor echoStderrLive): render EVERY log event to our
            // stderr. renderJobEvent's replay filter (error/warning only)
            // exists for detached-job replays; hiding info-level diagnostics
            // here made real failures unreadable — a renet child exited 1 and
            // every explanatory line was an info-level log event.
            routeLogEvent(frame.event, rememberLog);
          }
          return;
        case 'jobStarted':
          options.onJobStarted?.(frame.jobId);
          return;
        case 'result':
          finish(() => {
            // The job failed, so the diagnostics we withheld are exactly what the
            // reader needs. Flush BEFORE the step summary so cause precedes effect.
            if (frame.result.exitCode !== 0) flushDeferredLogs();
            renderCliSteps(options, frame.result);
            resolve(frame.result);
          });
          return;
        case 'error':
          finish(() => {
            flushDeferredLogs();
            reject(accepted ? new Error(frame.message) : new DaemonUnavailable(frame.message));
          });
          return;
        default:
          return;
      }
    });

    socket.on('data', (chunk) => read(chunk));
    socket.on('error', () =>
      finish(() =>
        reject(
          accepted
            ? new Error('daemon connection lost before result')
            : new DaemonUnavailable('socket error before accept')
        )
      )
    );
    socket.on('close', () =>
      finish(() =>
        reject(
          accepted
            ? new Error('daemon connection closed before result')
            : new DaemonUnavailable('socket closed before accept')
        )
      )
    );

    socket.write(encodeFrame({ type: 'hello', token, identity: deps.identity }));
    socket.write(encodeFrame({ type: 'execute', id, options: toWireOptions(options) }));
  });
}

/**
 * Send a control frame (`stop`/`status`) to a running daemon and return its first
 * substantive reply, or null when no daemon is listening. Never spawns one — a
 * control command has nothing to warm.
 */
export async function sendDaemonControl(
  frame: StopFrame | StatusFrame,
  deps: DaemonClientDeps = {}
): Promise<ServerFrame | null> {
  const socketPath = deps.socketPath ?? daemonSocketPath();
  const identity = deps.identity ?? processIdentity();
  const socket = await tryConnect(socketPath);
  if (!socket) return null;
  const token = readToken(tokenPathFor(socketPath)) ?? '';

  return new Promise<ServerFrame | null>((resolve) => {
    let settled = false;
    const finish = (value: ServerFrame | null): void => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(value);
    };

    const read = createFrameReader<ServerFrame>((reply) => {
      if (reply.type === 'helloOk') {
        socket.write(encodeFrame(frame));
        return;
      }
      finish(reply);
    });

    socket.on('data', (chunk) => read(chunk));
    socket.on('error', () => finish(null));
    socket.on('close', () => finish(null));

    // The control frame is sent once helloOk arrives; a stale daemon answers
    // `stale` first, which finish() returns as-is.
    socket.write(encodeFrame({ type: 'hello', token, identity }));
  });
}
