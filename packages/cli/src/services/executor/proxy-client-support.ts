/**
 * The pure parts of the `--proxy` client: its two error classes and the small
 * helpers that hold no client state (request timeout, host and failure text for
 * a wrapped network error, the Web Crypto buffer view, page delivery).
 */

import type { JobPollResponse } from '@rediacc/shared/cli-contract/wire';
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
export function hostOf(url: string): string {
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
export function describeFetchFailure(error: unknown): string {
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
