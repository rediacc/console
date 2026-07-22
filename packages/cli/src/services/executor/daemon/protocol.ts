/**
 * The executor-daemon wire protocol: NDJSON frames over a unix-domain socket.
 *
 * The daemon amortises per-process cold costs (SSH handshake, renet provision
 * checks, warm caches) across consecutive short-lived `rdc` invocations by
 * running the actual `localExecutorService.execute()` in one long-lived process
 * that consecutive clients talk to. This module holds the PURE half — the frame
 * shapes, the NDJSON codec, and the serializability gate — with no I/O, so it is
 * exercisable without a socket.
 *
 * The event payload is the very same `RenetEvent` the events-mode NDJSON contract
 * already streams (job-client.ts / createEventLineReader): the daemon forces the
 * server-side execute into events mode and relays each event as a frame, so the
 * client's render path is identical to the direct one.
 *
 * WHY a same-host daemon works where the remote `--proxy` executor did not: the
 * proxy client held NO config, so a command's action body died reading the
 * repository long before the seam. The daemon runs on the SAME host and shares
 * the same config files, so the action body reads config exactly as it does
 * today; only the execute() call at the seam crosses the socket.
 */

import type { ExecuteOptions, ExecuteResult, RenetEvent } from '../types.js';

/**
 * The serializable subset of ExecuteOptions that crosses the socket. The two
 * callback fields never travel: `onEvent` is realized as `event` frames the
 * client re-emits, and `onJobStarted` as a `jobStarted` frame.
 */
export type WireExecuteOptions = Omit<ExecuteOptions, 'onEvent' | 'onJobStarted'>;

/** The callback fields that are transported as frames rather than serialized. */
const TRANSPORTED_CALLBACK_KEYS = ['onEvent', 'onJobStarted'] as const;

// ---- client -> server -------------------------------------------------------

/** First frame on every connection: authenticates and version-stamps the client. */
interface HelloFrame {
  type: 'hello';
  /** The token the server wrote next to the socket; a mismatch closes the link. */
  token: string;
  /** VERSION plus (dev only) the cli-bundle stat fingerprint. */
  identity: string;
}

/** Ask the daemon to run one execute() on the client's behalf. */
interface ExecuteFrame {
  type: 'execute';
  id: string;
  options: WireExecuteOptions;
}

/** Best-effort request to abandon an in-flight execute (advisory). */
interface CancelFrame {
  type: 'cancel';
  id: string;
}

/** Ask the daemon to drain in-flight work and exit. */
export interface StopFrame {
  type: 'stop';
}

/** Ask the daemon to report its pid, uptime, identity, and warm hosts. */
export interface StatusFrame {
  type: 'status';
}

export type ClientFrame = HelloFrame | ExecuteFrame | CancelFrame | StopFrame | StatusFrame;

// ---- server -> client -------------------------------------------------------

/** The server has begun running the execute; from here a drop must NOT re-run it. */
interface AcceptedFrame {
  type: 'accepted';
  id: string;
}

/** One relayed renet event, carrying the optional spool-line ordinal. */
interface EventFrame {
  type: 'event';
  id: string;
  event: RenetEvent;
  line?: number;
}

/** A detached run's job id, relayed for onJobStarted. */
interface JobStartedFrame {
  type: 'jobStarted';
  id: string;
  jobId: string;
}

/** The terminal ExecuteResult for one execute. */
interface ResultFrame {
  type: 'result';
  id: string;
  result: ExecuteResult;
}

/** A per-execute failure (thrown from execute() on the server). */
interface ErrorFrame {
  type: 'error';
  id: string;
  message: string;
}

/** The client's identity does not match the running daemon: it will exit; retry fresh. */
interface StaleFrame {
  type: 'stale';
}

/** Acknowledges a valid hello (sent before any execute is accepted). */
interface HelloOkFrame {
  type: 'helloOk';
}

/** Answer to a status frame. */
interface StatusInfoFrame {
  type: 'statusInfo';
  pid: number;
  uptimeMs: number;
  identity: string;
  warmHosts: string[];
}

/** Acknowledges a stop frame; the daemon exits after draining. */
interface StoppingFrame {
  type: 'stopping';
}

export type ServerFrame =
  | AcceptedFrame
  | EventFrame
  | JobStartedFrame
  | ResultFrame
  | ErrorFrame
  | StaleFrame
  | HelloOkFrame
  | StatusInfoFrame
  | StoppingFrame;

export type Frame = ClientFrame | ServerFrame;

// ---- codec ------------------------------------------------------------------

/** Serialize a frame as one NDJSON line (trailing newline included). */
export function encodeFrame(frame: Frame): string {
  return `${JSON.stringify(frame)}\n`;
}

/**
 * A stateful NDJSON reader. Feed it socket chunks; it invokes `onFrame` once per
 * complete line. A partial trailing line is buffered until its newline arrives,
 * so a frame split across two chunks is never handed over half-parsed. A line
 * that does not parse is dropped (a trusted local peer should never send one; a
 * stray byte must not crash the reader).
 */
export function createFrameReader<T = Frame>(onFrame: (frame: T) => void): (chunk: Buffer | string) => void {
  let buffered = '';
  return (chunk: Buffer | string): void => {
    buffered += chunk.toString();
    const lines = buffered.split('\n');
    buffered = lines.pop() ?? '';
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        onFrame(JSON.parse(trimmed) as T);
      } catch {
        // A malformed line is dropped rather than throwing: the socket peer is
        // trusted, so this only guards against a stray/truncated byte.
      }
    }
  };
}

// ---- serializability gate ---------------------------------------------------

/** Strip the transported callbacks, leaving the payload that crosses the socket. */
export function toWireOptions(options: ExecuteOptions): WireExecuteOptions {
  const wire = { ...options };
  delete wire.onEvent;
  delete wire.onJobStarted;
  return wire;
}

/**
 * Whether `value` holds anything JSON cannot faithfully carry. Functions and
 * symbols are silently DROPPED by JSON.stringify (a lost callback would run
 * nowhere), and a bigint THROWS, so any of them means "not serializable".
 */
function containsNonSerializable(value: unknown, seen: Set<object> = new Set()): boolean {
  if (value === null) return false;
  const kind = typeof value;
  if (kind === 'function' || kind === 'symbol' || kind === 'bigint') return true;
  if (kind !== 'object') return false;
  const obj = value as object;
  if (seen.has(obj)) return false;
  seen.add(obj);
  if (Array.isArray(obj)) return obj.some((v) => containsNonSerializable(v, seen));
  return Object.values(obj).some((v) => containsNonSerializable(v, seen));
}

/**
 * Whether these options may cross the socket to the daemon.
 *
 * The two transported callbacks (`onEvent`, `onJobStarted`) are IGNORED here —
 * they become frames. Any OTHER non-serializable member (an unexpected callback,
 * a custom stream, a bigint) means the command carries something the daemon
 * cannot reproduce, so the caller must route it to the DIRECT executor instead.
 */
export function isDaemonSerializable(options: ExecuteOptions): boolean {
  return !containsNonSerializable(toWireOptions(options));
}
