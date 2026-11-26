/**
 * The pure parts of the `--proxy` client: its error classes (version mismatch
 * and the 409 reader that raises it, truncated stream, unknown session, a failed
 * request) and the small helpers that hold
 * no client state (request timeout and fetchWithTimeout, the session-unknown
 * check, host and failure text for a wrapped network error and whether that
 * request can have reached the executor, the Web Crypto buffer view, page
 * delivery).
 */

import { type JobPollResponse, VersionMismatchSchema } from '@rediacc/shared/cli-contract/wire';
import { t } from '../../i18n/index.js';
import { ERROR_CODES } from '../../types/errors.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import { isTerminalState } from './proxy-follow.js';
import type { RenetEvent } from './types.js';

/** Raised when the executor rejects the client's contract version. */
export class ProxyVersionMismatchError extends Error {
  constructor(
    readonly clientContractVersion: string,
    readonly executorContractVersion: string,
    readonly executorCliVersion: string
  ) {
    super(
      `Proxy executor speaks contract ${executorContractVersion} (rdc ${executorCliVersion}), ` +
        `this client speaks ${clientContractVersion}. Upgrade rdc, or point --proxy at a matching executor.`
    );
    this.name = 'ProxyVersionMismatchError';
  }
}

/** A 409 from the executor: the versions its body names, or this client's against "unknown" when the body says nothing readable. */
export async function throwVersionMismatch(
  response: Response,
  clientContractVersion: string
): Promise<never> {
  const body = VersionMismatchSchema.safeParse(await response.json().catch(() => ({})));
  if (body.success) {
    throw new ProxyVersionMismatchError(
      body.data.clientContractVersion,
      body.data.executorContractVersion,
      body.data.executorCliVersion
    );
  }
  throw new ProxyVersionMismatchError(clientContractVersion, 'unknown', 'unknown');
}

/** Raised when the executor closes the stream without a terminal result line. */
export class ProxyStreamTruncatedError extends Error {
  constructor(readonly eventsSeen: number) {
    super(
      `The proxy closed the stream after ${eventsSeen} event(s) without reporting a result. ` +
        `The operation may still be running on the machine. Check its status before retrying.`
    );
    this.name = 'ProxyStreamTruncatedError';
  }
}

/** An ArrayBuffer view Web Crypto accepts, from a Uint8Array that may be a slice. */
export function toArrayBuffer(data: Uint8Array): ArrayBuffer {
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

/**
 * How long the executor has to ANSWER a request (the response headers) before the client gives up.
 *
 * It bounds the request phase only: the clock stops when the headers arrive, so a command that streams for
 * minutes is never cut. A minute covers an executor that does real work (license recovery, a session grant)
 * before it flushes headers, and still turns a stalled one into an error instead of a hang. Override with
 * REDIACC_PROXY_TIMEOUT_MS (milliseconds), or `timeoutMs` in the options.
 */
const DEFAULT_PROXY_REQUEST_TIMEOUT_MS = 60_000;

/** The host of a request URL; an unparseable URL yields its text up to any query or fragment, so the wrapped network error is never replaced by a URL TypeError and a query token is never echoed. */
function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url.split(/[?#]/, 1)[0];
  }
}

/** The request timeout from the environment, or the default when unset or not a positive number. */
export function proxyRequestTimeoutMs(): number {
  const raw = Number(process.env.REDIACC_PROXY_TIMEOUT_MS);
  return Number.isFinite(raw) && raw > 0 ? raw : DEFAULT_PROXY_REQUEST_TIMEOUT_MS;
}

/** What went wrong in a failed fetch, from undici's `cause` ("ECONNREFUSED", "ENOTFOUND", ...) when it has one. */
function describeFetchFailure(error: unknown): string {
  const cause = error instanceof Error ? error.cause : undefined;
  const source = cause ?? error;
  if (!(source instanceof Error)) return String(source);
  const code = (source as { code?: unknown }).code;
  if (typeof code !== 'string') return source.message || source.name;
  // An AggregateError (one refusal per resolved address) has an empty message; the code says it all.
  return source.message && source.message !== code ? `${code} (${source.message})` : code;
}

/** Hand a page's events to the renderer, with their 1-based spool ordinals. True when the page ends the job. */
export function deliverPage(
  poll: JobPollResponse,
  onEvent: (event: RenetEvent, line?: number) => void
): boolean {
  for (const entry of poll.events) onEvent(entry.event, entry.line + 1);
  return isTerminalState(poll.status.state) && !poll.more;
}

/** The executor's wire code for a session it does not hold (packages/cli/src/services/serve/sessions.ts). */
const SESSION_UNKNOWN_CODE = 'EXECUTOR_SESSION_UNKNOWN';

/** A command the executor refused because it no longer holds the named session. */
export class ExecutorSessionUnknownError extends Error {
  constructor(readonly detail: string) {
    super(detail);
    this.name = 'ExecutorSessionUnknownError';
  }
}

/**
 * Failure codes that end a request before any byte of it reaches the executor: the name did not resolve, nothing
 * accepted the connection, no route led to the host, or the TLS handshake failed. undici reports each on the fetch
 * error's `cause` (an AggregateError per resolved address carries one per address).
 */
const CONNECT_PHASE_CODES = new Set([
  'ECONNREFUSED',
  'ENOTFOUND',
  'EAI_AGAIN',
  'EAI_NONAME',
  'EHOSTUNREACH',
  'ENETUNREACH',
  'EADDRNOTAVAIL',
  'UND_ERR_CONNECT_TIMEOUT',
]);

/**
 * A TLS failure that ends the handshake: undici's `ERR_TLS_*`, OpenSSL's certificate verdicts (`CERT_HAS_EXPIRED`,
 * `SELF_SIGNED_CERT_IN_CHAIN`, ...) and the `ERR_SSL_*` records a handshake raises. Other `ERR_SSL_*` codes (bad record
 * MAC, decryption failed, alerts) can hit an established keep-alive connection mid-request, so they stay unknown.
 */
const TLS_CODE =
  /^ERR_TLS_|CERT|^ERR_SSL_(WRONG_VERSION_NUMBER|UNKNOWN_PROTOCOL|UNSUPPORTED_PROTOCOL|NO_PROTOCOLS_AVAILABLE|WRONG_SSL_VERSION|(SSLV3|TLSV1)_ALERT_HANDSHAKE_FAILURE|TLSV1_ALERT_PROTOCOL_VERSION)$/;

function isConnectPhaseCode(code: unknown): boolean {
  return typeof code === 'string' && (CONNECT_PHASE_CODES.has(code) || TLS_CODE.test(code));
}

/**
 * Whether a failed fetch can have delivered the request: false only when undici's cause names a connect-phase failure
 * (for an AggregateError, every address failed that way), true for anything else: a reset, a socket closed
 * mid-request, a deadline hit while waiting for the headers, or a failure with no code to read.
 */
export function fetchMayHaveReached(error: unknown, timedOut: boolean): boolean {
  if (timedOut) return true;
  const cause = error instanceof Error ? error.cause : undefined;
  if (!(cause instanceof Error)) return true;
  if (cause instanceof AggregateError && cause.errors.length > 0) {
    return !cause.errors.every((each) => isConnectPhaseCode((each as { code?: unknown }).code));
  }
  return !isConnectPhaseCode((cause as { code?: unknown }).code);
}

/**
 * The NETWORK_ERROR a failed proxy request raises. `mayHaveReached` is false only when the request provably never
 * reached the executor, so nothing it asked for can have started and a caller that registered state ahead of a job
 * (repo create, repo fork) may roll it back; true leaves the job's state unknown.
 */
export class ProxyRequestError extends CliExitError {
  readonly mayHaveReached: boolean;

  constructor(message: string, mayHaveReached: boolean, cause: unknown) {
    super(ERROR_CODES.NETWORK_ERROR, message, { retryable: true });
    this.mayHaveReached = mayHaveReached;
    this.cause = cause;
  }
}

/** The same failure marked as possibly delivered: a last attempt that never connected does not undo an earlier attempt that may have. */
export function asMayHaveReached(error: unknown): unknown {
  if (!(error instanceof ProxyRequestError) || error.mayHaveReached) return error;
  return new ProxyRequestError(error.message, true, error.cause);
}

/**
 * Note a failed command-start POST on `reach` and return the error to raise when no retry is left. Once any attempt
 * may have delivered its POST, a last attempt that never connected says nothing about the job the earlier one may
 * have started, so the failure is raised as possibly delivered.
 */
export function noteStartFailure(error: unknown, reach: { reached: boolean }): unknown {
  if (error instanceof ProxyRequestError && error.mayHaveReached) reach.reached = true;
  return reach.reached ? asMayHaveReached(error) : error;
}

/** `fetchImpl(url, init)` with a deadline; a timeout or a network failure becomes a retryable {@link ProxyRequestError} naming the host and saying whether the request can have reached the executor. */
export async function fetchWithTimeout(
  fetchImpl: typeof fetch,
  timeoutMs: number,
  url: string,
  init: RequestInit
): Promise<Response> {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    return await fetchImpl(url, { ...init, signal: controller.signal });
  } catch (error) {
    const host = hostOf(url);
    const message = timedOut
      ? t('errors.proxy.timeout', { host, seconds: Math.ceil(timeoutMs / 1000) })
      : t('errors.proxy.unreachable', { host, reason: describeFetchFailure(error) });
    throw new ProxyRequestError(message, fetchMayHaveReached(error, timedOut), error);
  } finally {
    clearTimeout(timer);
  }
}

/** A 404 carrying EXECUTOR_SESSION_UNKNOWN becomes the error the re-grant catches; any other 404 is described as before. */
export async function throwIfSessionUnknown(response: Response): Promise<void> {
  const text = await response.clone().text();
  let code: unknown;
  try {
    code = (JSON.parse(text) as { code?: unknown }).code;
  } catch {
    // Not JSON: an ordinary 404, described by the caller.
    return;
  }
  if (code === SESSION_UNKNOWN_CODE) throw new ExecutorSessionUnknownError(text.slice(0, 500));
}

/** Turn a non-OK response into an operator-readable message. */
export async function describeProxyFailure(response: Response): Promise<string> {
  const text = await response.text().catch(() => '');
  const detail = text.slice(0, 500);

  if (response.status === 401 || response.status === 403) {
    return `Proxy rejected this request (${response.status}). The token may be expired, or policy may not allow this command. ${detail}`;
  }
  return `Proxy request failed (${response.status} ${response.statusText}). ${detail}`;
}
