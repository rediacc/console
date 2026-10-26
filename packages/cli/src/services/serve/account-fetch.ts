/**
 * The executor's calls to the account server (introspection, audit events,
 * config and grant records) are short JSON round trips. Each gets a deadline so
 * a stalled account server fails the request instead of hanging it, and a
 * network failure keeps undici's cause (ECONNREFUSED, ENOTFOUND, ...) rather
 * than the bare "fetch failed".
 */

/** How long one account-server round trip may take. */
export const ACCOUNT_REQUEST_TIMEOUT_MS = 15_000;

/** `init` with a deadline signal. A signal the caller set is kept as is and opts that call out of the deadline: the caller owns its cancellation. */
export function withAccountDeadline(init: RequestInit = {}): RequestInit {
  return init.signal ? init : { ...init, signal: AbortSignal.timeout(ACCOUNT_REQUEST_TIMEOUT_MS) };
}

/** The message of a failed fetch with its cause appended: "fetch failed (ECONNREFUSED)". */
export function describeFetchError(error: unknown): string {
  if (!(error instanceof Error)) return String(error);
  const cause = (error as Error & { cause?: unknown }).cause as
    | { code?: unknown; message?: unknown }
    | undefined;
  const code = typeof cause?.code === 'string' ? cause.code : undefined;
  const detail = code ?? (typeof cause?.message === 'string' ? cause.message : undefined);
  return detail && !error.message.includes(detail) ? `${error.message} (${detail})` : error.message;
}

/** `fetchImpl` with the account deadline added to every call it makes. */
export function deadlineFetch(fetchImpl: typeof globalThis.fetch): typeof globalThis.fetch {
  return (input, init) => fetchImpl(input, withAccountDeadline(init));
}
