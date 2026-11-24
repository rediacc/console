/**
 * The pure parts of the `--proxy` client: its three error classes (version
 * mismatch, truncated stream, unknown session) and the small helpers that hold
 * no client state (request timeout and fetchWithTimeout, the session-unknown
 * check, host and failure text for a wrapped network error, the Web Crypto
 * buffer view, page delivery).
 */

import type { JobPollResponse } from '@rediacc/shared/cli-contract/wire';
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

/** `fetchImpl(url, init)` with a deadline; a timeout or a network failure becomes a retryable NETWORK_ERROR naming the host. */
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
    const failure = new CliExitError(ERROR_CODES.NETWORK_ERROR, message, { retryable: true });
    failure.cause = error;
    throw failure;
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
