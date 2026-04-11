/**
 * OTLP credential resolver for runtime telemetry.
 *
 * On the first call of a CLI process, fetches per-region OTLP basicauth
 * credentials from `GET /account/api/v1/telemetry/config` (unauthenticated)
 * and caches the result in memory for the rest of the process lifetime.
 * Subsequent calls are zero-cost.
 *
 * The credentials are used to:
 *   1. Enable the CLI's own OpenTelemetry exporters (see `telemetry.ts`).
 *   2. Inject `REDIACC_OTLP_USER` / `REDIACC_OTLP_PASS` env vars when
 *      spawning renet via SSH (see `local-executor.ts`).
 *
 * Regional routing: each regional account worker holds its own
 * `OTLP_CLIENT_CREDENTIALS` Worker secret. Clients get the correct
 * credential based on which regional URL their account-server config
 * points to — no per-client logic needed.
 *
 * Default-deny: if the endpoint returns `{otlp: null}`, the network fails,
 * or the account server is unreachable, this function returns `null` and
 * every downstream consumer treats telemetry as disabled. No unauthenticated
 * OTLP requests are ever sent.
 *
 * Security: credentials live in memory for the process lifetime only. They
 * are NEVER persisted to disk on the client side — not to `~/.config/rediacc`,
 * not to any temp file, not anywhere. The only place they can be stored is
 * in the memory of the process that fetched them and, transiently, in the
 * env vars of a spawned renet process (which is also memory-only).
 */

import { accountServerFetch } from './account-client.js';

export interface OtlpCredentials {
  endpoint: string;
  user: string;
  pass: string;
}

interface TelemetryConfigResponse {
  otlp: OtlpCredentials | null;
}

/** In-process cache — `undefined` = not yet fetched, `null` = fetched & disabled. */
let cached: OtlpCredentials | null | undefined;

/**
 * Fetch the current OTLP credentials from the account server.
 *
 * Returns `null` when:
 *   - The endpoint returns `{otlp: null}` (region has no credential configured)
 *   - The request fails (network error, 4xx, 5xx, account server unreachable)
 *   - The response is malformed
 *
 * Never throws. Telemetry failures must never interfere with the user's
 * actual command — the CLI must always degrade to "telemetry disabled"
 * rather than surfacing an error.
 */
export async function fetchOtlpCredentials(): Promise<OtlpCredentials | null> {
  if (cached !== undefined) return cached;

  try {
    const resp = await accountServerFetch<TelemetryConfigResponse>(
      '/account/api/v1/telemetry/config',
      { noAuth: true }
    );
    cached = resp.otlp ?? null;
  } catch {
    cached = null;
  }
  return cached;
}

/**
 * Reset the in-process cache. Used only in tests — production code should
 * never need to invalidate the cache since each CLI invocation is a fresh
 * process with a fresh cache.
 */
export function resetOtlpCredentialsCache(): void {
  cached = undefined;
}

/**
 * Convert `{user, pass}` to the base64 `Basic <...>` token format used by
 * the CLI's OTel exporter and renet's basicauth header builder.
 */
export function credentialsToBasicAuthToken(creds: OtlpCredentials): string {
  return Buffer.from(`${creds.user}:${creds.pass}`).toString('base64');
}
