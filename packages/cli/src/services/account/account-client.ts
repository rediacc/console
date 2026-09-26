/**
 * Account Server Client
 *
 * Centralized HTTP client for all CLI → account server communication.
 * All requests are E2E encrypted via X25519 ECDH + AES-256-GCM tunnel.
 */

import { API_VERSION_DEFAULTS } from '@rediacc/shared/config/defaults';
import {
  CURRENT_SERVER_E2E_KEY,
  E2E_CONTENT_TYPE,
  type E2eResponseEnvelope,
  importX25519PublicKey,
  openResponse,
  sealRequest,
} from '@rediacc/shared/e2e';
import {
  API_TOKEN_IP_REBIND_PATH,
  type ApiTokenIpRebindRequest,
  type ApiTokenIpRebindResponse,
  TOKEN_IP_MISMATCH,
  type TokenIpRebindHint,
} from '@rediacc/shared/subscription/types';
import { t } from '../../i18n/index.js';
import { ValidationError } from '../../utils/errors.js';
import { getInstallMethod, getNpmUpdateCommand } from '../../utils/platform.js';
import { VERSION } from '../../version.js';
import { getEffectiveConfigName } from '../config/config-name.js';
import { updateConfigAtPointer } from '../config/synced-write.js';
import { writeStderr } from '../core/request-context.js';
import { resolveChannel } from '../update/updater.js';
import { readAccountPointer } from './account-pointer.js';
import {
  getSubscriptionServerUrl,
  getSubscriptionTokenState,
  normalizeServerUrl,
} from './subscription-auth.js';
import { ensureRebound } from './token-ip-rebind.js';

/** Cached server key material (imported once per process). */
let serverKeyCache: {
  key: Awaited<ReturnType<typeof importX25519PublicKey>>;
  keyId: string;
} | null = null;

export async function getServerKeyMaterial() {
  if (!serverKeyCache) {
    // 1. Config account.e2ePublicKey (seeded by install script or a prior `subscription login --server`, or discovered-and-cached below)
    const pointerKey = readAccountPointer().e2ePublicKey;
    if (pointerKey) {
      serverKeyCache = {
        key: await importX25519PublicKey(pointerKey),
        keyId: 'config',
      };
      return serverKeyCache;
    }

    // 2. Runtime discovery from server's .well-known endpoint
    const discoveredKey = await discoverServerKey();
    if (discoveredKey) {
      serverKeyCache = {
        key: await importX25519PublicKey(discoveredKey.publicKeySpki),
        keyId: discoveredKey.keyId,
      };
      return serverKeyCache;
    }

    // 3. Hardcoded production key (fallback)
    serverKeyCache = {
      key: await importX25519PublicKey(CURRENT_SERVER_E2E_KEY.publicKeySpki),
      keyId: CURRENT_SERVER_E2E_KEY.keyId,
    };
  }
  return serverKeyCache;
}

/** Fetch the server's E2E public key from its .well-known endpoint. */
async function discoverServerKey(): Promise<{
  keyId: string;
  publicKeySpki: string;
} | null> {
  try {
    const serverUrl = getSubscriptionServerUrl();
    const resp = await fetch(`${serverUrl}/account/api/v1/.well-known/server-info`, {
      signal: AbortSignal.timeout(5000),
    });
    if (!resp.ok) return null;
    const info = (await resp.json()) as {
      e2e?: { keys?: { keyId: string; publicKeySpki: string }[] };
    };
    const key = info.e2e?.keys?.[0];
    if (!key?.publicKeySpki) return null;

    // Cache in the active config for next startup, but only when the pointer had none. Guarded: the config file may not exist yet on a fresh machine (discovery still returns the key regardless).
    // The key is device-local (DEVICE_LOCAL_POINTERS), so this is a write to this device's file for a remote config too: no push, and so no pull re-entering this lookup.
    const configName = getEffectiveConfigName();
    if (!readAccountPointer(configName).e2ePublicKey) {
      try {
        await updateConfigAtPointer(configName, '/account/e2ePublicKey', (cfg) => ({
          ...cfg,
          account: { ...(cfg.account ?? {}), e2ePublicKey: key.publicKeySpki },
        }));
      } catch {
        // Config may not exist yet; discovery result still stands.
      }
    }

    return key;
  } catch {
    return null;
  }
}

/** Default HTTP method for account server requests. */
const DEFAULT_HTTP_METHOD = 'GET';

export interface AccountFetchOptions {
  /** HTTP method (default: GET) */
  method?: string;
  /** Request body (will be JSON-serialized) */
  body?: unknown;
  /** Explicit Bearer token (bypasses stored token lookup) */
  token?: string;
  /** Explicit server URL (bypasses stored token/config lookup) */
  serverUrl?: string;
  /** Skip authentication header entirely (for unauthenticated endpoints) */
  noAuth?: boolean;
  /**
   * Offer to move the token to this IP when the server answers TOKEN_IP_MISMATCH
   * (default true). Background callers (audit flush, telemetry) pass false: a
   * prompt during a timed-out send or an exit flush would be wrong.
   */
  ipRebind?: boolean;
  /**
   * Test seam: the fetch that carries the tunnel request (the rebind and the retry included).
   * Production passes nothing and the global fetch is used; the config-sync harness routes each
   * device through its own client address.
   */
  fetchImpl?: typeof fetch;
  /** Test seam: the server's E2E key. Production passes nothing and getServerKeyMaterial() resolves it. */
  serverKey?: { key: CryptoKey; keyId: string };
}

export interface AccountFetchError extends Error {
  status: number;
  code?: string;
  /** The parsed inner error body (`rebind`, `retryAfter`, `attemptsRemaining`, `reason`, ...). */
  details?: Record<string, unknown>;
}

/**
 * Fetch server-info from an account server (unauthenticated, no tunnel).
 * Used during login to auto-sync update channel and discover e2e keys.
 */
export interface ServerInfo {
  e2e: { keys: { keyId: string; publicKeySpki: string }[] };
  apiVersion: number;
  minCliVersion: string;
  warnCliVersion: string | null;
  environment: string;
  updateChannel?: string;
}

export async function fetchServerInfo(serverUrl: string): Promise<ServerInfo> {
  const url = `${normalizeServerUrl(serverUrl)}/account/api/v1/.well-known/server-info`;
  const res = await fetch(url, {
    headers: { 'User-Agent': `rdc/${VERSION}` },
    signal: AbortSignal.timeout(5000),
  });
  if (!res.ok) throw new Error(`server-info returned ${res.status}`);
  return res.json() as Promise<ServerInfo>;
}

/** Handle 426 (CLI upgrade required) response from the account server. */
function handle426Response(
  parsed: { error?: string; minVersion?: string; currentVersion?: string; updateChannel?: string },
  method: string
): never {
  const currentChannel = resolveChannel();
  const serverChannel = parsed.updateChannel;
  const lines = [
    parsed.error ?? API_VERSION_DEFAULTS.UPGRADE_ERROR_MSG,
    '',
    `  Current: ${parsed.currentVersion ?? VERSION}`,
    `  Required: ${parsed.minVersion ?? API_VERSION_DEFAULTS.UNKNOWN_VERSION}`,
  ];
  if (serverChannel && serverChannel !== currentChannel) {
    lines.push(`  Channel: ${currentChannel} (server recommends: ${serverChannel})`);
    const updateCmd =
      method === 'sea'
        ? `rdc update --channel ${serverChannel}`
        : getNpmUpdateCommand(serverChannel);
    lines.push(`  Fix: ${updateCmd}`);
  } else {
    const updateCmd = method === 'sea' ? 'rdc update' : getNpmUpdateCommand(currentChannel);
    lines.push(`  Update: ${updateCmd}`);
  }
  const msg = lines.join('\n');
  writeStderr(`\n${msg}\n\n`);
  throw createAccountError(msg, 426, 'CLI_UPGRADE_REQUIRED');
}

/**
 * Send an E2E-encrypted request to the account server.
 *
 * All requests go through POST /account/api/v1/tunnel.
 * The original method, path, headers, and body are encrypted inside the envelope.
 *
 * @param path - API path (e.g. '/account/api/v1/licenses/status')
 * @param options - Request options
 * @returns Parsed JSON response body
 * @throws AccountFetchError on non-2xx responses
 * @throws Error on encryption/network failures
 */
export async function accountServerFetch<T = unknown>(
  path: string,
  options: AccountFetchOptions = {}
): Promise<T> {
  // Resolve the token once, so the rebind and the retry use the SAME token as the refused request (stored, REDIACC_TOKEN, or options.token).
  const token = options.noAuth ? undefined : (options.token ?? resolveStoredToken());
  const serverUrl = options.serverUrl ?? resolveServerUrl();
  try {
    return await accountServerFetchOnce<T>(path, options, token, serverUrl);
  } catch (error) {
    if (!isTokenIpMismatch(error) || token === undefined || options.ipRebind === false) {
      throw error;
    }
    return reboundRetry<T>(path, options, token, serverUrl, error);
  }
}

function isTokenIpMismatch(error: unknown): error is AccountFetchError {
  const e = error as Partial<AccountFetchError> | null;
  return e?.status === 403 && e.code === TOKEN_IP_MISMATCH;
}

/** Move the token to this IP (prompting on a TTY), then replay the refused request exactly once. */
async function reboundRetry<T>(
  path: string,
  options: AccountFetchOptions,
  token: string,
  serverUrl: string,
  refusal: AccountFetchError
): Promise<T> {
  const hint: TokenIpRebindHint = refusal.details?.rebind === 'relogin' ? 'relogin' : 'totp';
  await ensureRebound({
    token,
    hint,
    rebind: (code) =>
      accountServerFetchOnce<ApiTokenIpRebindResponse>(
        API_TOKEN_IP_REBIND_PATH,
        {
          method: 'POST',
          body: { code } satisfies ApiTokenIpRebindRequest,
          fetchImpl: options.fetchImpl,
          serverKey: options.serverKey,
        },
        token,
        serverUrl
      ),
  });
  // Exactly one retry. A second mismatch (say, IPv4 and IPv6 egress alternating) is reported, never prompted again.
  try {
    return await accountServerFetchOnce<T>(path, options, token, serverUrl);
  } catch (retryError) {
    if (!isTokenIpMismatch(retryError)) throw retryError;
    throw createAccountError(
      t('errors.subscription.ipRebind.stillMismatched'),
      403,
      TOKEN_IP_MISMATCH,
      retryError.details
    );
  }
}

/** Inner request headers: the CLI version, the bearer token when there is one, and the body type. */
function innerHeaders(token: string | undefined, hasBody: boolean): Record<string, string> {
  const headers: Record<string, string> = {
    'x-cli-version': VERSION,
  };
  if (token !== undefined) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  if (hasBody) {
    headers['Content-Type'] = 'application/json';
  }
  return headers;
}

/** One tunnel round trip with an already-resolved token (undefined sends no Authorization header). */
async function accountServerFetchOnce<T>(
  path: string,
  options: AccountFetchOptions,
  token: string | undefined,
  serverUrl: string
): Promise<T> {
  const method = options.method ?? DEFAULT_HTTP_METHOD;
  const headers = innerHeaders(token, options.body !== undefined);

  // Encrypt the request
  const { serverKey, keyId, send } = await tunnelTransport(options);
  const { envelope, aesKey } = await sealRequest(
    serverKey,
    keyId,
    method,
    path,
    headers,
    options.body ?? null
  );

  // Send through the tunnel
  const tunnelUrl = `${serverUrl}/account/api/v1/tunnel`;
  const resp = await send(tunnelUrl, {
    method: 'POST',
    headers: { 'Content-Type': E2E_CONTENT_TYPE },
    body: JSON.stringify(envelope),
  });

  // Tunnel-level errors (decryption failed, invalid envelope) are plain JSON
  if (!resp.ok) {
    const errorBody = await resp.json().catch(() => ({ error: `HTTP ${resp.status}` }));
    const msg = (errorBody as { error?: string }).error ?? `HTTP ${resp.status}`;
    throw createAccountError(msg, resp.status);
  }

  // Decrypt the response
  const responseEnvelope = (await resp.json()) as E2eResponseEnvelope;
  const { status, body } = await openResponse(aesKey, responseEnvelope);

  // Parse the decrypted response
  const parsed: T & { error?: string; code?: string } = body ? JSON.parse(body) : {};

  // Handle CLI upgrade required (426). Pre-release builds (e.g. "0.0.0-dev") are developer artifacts, their channel governs suitability, not the server's numeric min-version gate. Swallow the 426 silently so callers treat it as a no-op instead of printing a nonsensical "upgrade your dev build" banner.
  if (status === 426) {
    if (VERSION.includes('-')) {
      // Dev build: synthesize an empty result. `Object.create(null)` returns `any` so it's assignable to an arbitrary generic T without an object
      // literal assertion. Callers' `.catch(() => null)` paths don't run.
      return Object.create(null);
    }
    handle426Response(parsed, getInstallMethod());
  }

  // Check the inner HTTP status
  if (status >= 400) {
    const msg = (parsed as { error?: string }).error ?? `Account server returned HTTP ${status}`;
    const code = (parsed as { code?: string }).code;
    throw createAccountError(msg, status, code, parsed);
  }

  return parsed;
}

/** The server key and the fetch a tunnel request uses: the test seams when given, else production's. */
async function tunnelTransport(options: AccountFetchOptions) {
  const { key: serverKey, keyId } = options.serverKey ?? (await getServerKeyMaterial());
  return { serverKey, keyId, send: options.fetchImpl ?? fetch };
}

function resolveServerUrl(): string {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind === 'ready') {
    return tokenState.serverUrl;
  }
  return getSubscriptionServerUrl();
}

function resolveStoredToken(): string {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    throw new ValidationError(t('errors.subscription.tokenRequired'));
  }
  return tokenState.token.token;
}

function createAccountError(
  message: string,
  status: number,
  code?: string,
  details?: Record<string, unknown>
): AccountFetchError {
  const error = new Error(message) as AccountFetchError;
  error.status = status;
  if (code) error.code = code;
  if (details) error.details = details;
  return error;
}
