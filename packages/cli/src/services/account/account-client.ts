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
import { BAKED_IN_REGIONS } from '@rediacc/shared/regions';
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
import { type AccountPointer, readAccountPointer } from './account-pointer.js';
import {
  getSubscriptionServerUrl,
  getSubscriptionTokenState,
  normalizeServerUrl,
} from './subscription-auth.js';
import { ensureRebound } from './token-ip-rebind.js';

type ServerKeyMaterial = {
  key: Awaited<ReturnType<typeof importX25519PublicKey>>;
  keyId: string;
};

/**
 * No E2E key is known for the server a request goes to: the active config saved none for it, and
 * its server-info either could not be read (`unreachable`, `cause` keeps the failure, so a network
 * error still classifies as unreachable) or was read and advertised no key (`no-key`). Raised
 * instead of sealing with the baked-in key, which only the production regions hold: against any
 * other server that request fails as a bare "Decryption failed" naming nothing (vm:check license
 * drill, 2026-10-21).
 */
export class ServerE2eKeyUnavailableError extends Error {
  readonly serverUrl: string;
  readonly reason: 'unreachable' | 'no-key';
  constructor(serverUrl: string, reason: 'unreachable' | 'no-key', options?: { cause?: unknown }) {
    const cause = options?.cause;
    const why =
      reason === 'no-key'
        ? 'its server-info advertises no E2E key'
        : `its server-info could not be read${cause === undefined ? '' : `: ${cause instanceof Error ? cause.message : String(cause)}`}`;
    const remedy =
      reason === 'no-key'
        ? 'the server is misconfigured; check its X25519 key'
        : `run "rdc subscription login --server ${serverUrl}" once the server answers`;
    super(
      `No E2E key for account server ${serverUrl}: the active config holds none for it and ${why}. The baked-in key belongs to the production regions only; ${remedy}.`,
      options
    );
    this.name = 'ServerE2eKeyUnavailableError';
    this.serverUrl = serverUrl;
    this.reason = reason;
  }
}

/** The production regional origins, the only servers the baked-in key belongs to. */
function isProductionServer(serverUrl: string): boolean {
  return BAKED_IN_REGIONS.some((region) => serverUrl === `https://${region.domain}`);
}

/** Imported keys by SPKI: an import happens once per key per process, while WHICH key a request uses is resolved on every call. */
const importedKeys = new Map<string, ReturnType<typeof importX25519PublicKey>>();

function importKeyOnce(publicKeySpki: string): ReturnType<typeof importX25519PublicKey> {
  let imported = importedKeys.get(publicKeySpki);
  if (!imported) {
    imported = importX25519PublicKey(publicKeySpki);
    importedKeys.set(publicKeySpki, imported);
  }
  return imported;
}

/** Keys discovered from each server this process asked, by normalized server URL. */
const discoveredKeys = new Map<string, { keyId: string; publicKeySpki: string }>();

/**
 * The E2E key for the server at `serverUrl`, the server the request is sent to.
 *
 * 1. The active config's `account.e2ePublicKey`, but only when the config's `accountServer` is
 *    this server: a key is the property of the server it was fetched from.
 * 2. Discovery from this server's `.well-known/server-info`.
 * 3. The baked-in key, for a production region only. Any other server without a key is a
 *    ServerE2eKeyUnavailableError.
 *
 * Nothing resolved from the config is cached in the process. A process-wide cache once let a
 * concurrent telemetry call pin a stale key before `subscription login` saved the right one, so
 * the login itself then sealed with the stale key.
 */
export async function getServerKeyMaterial(serverUrl: string): Promise<ServerKeyMaterial> {
  const target = normalizeServerUrl(serverUrl);

  const pointer = readAccountPointer();
  if (
    pointer.e2ePublicKey &&
    pointer.accountServer !== undefined &&
    normalizeServerUrl(pointer.accountServer) === target
  ) {
    return { key: await importKeyOnce(pointer.e2ePublicKey), keyId: 'config' };
  }

  let failure: unknown;
  try {
    const discovered = await discoverServerKey(target, pointer);
    if (discovered) {
      return { key: await importKeyOnce(discovered.publicKeySpki), keyId: discovered.keyId };
    }
  } catch (error) {
    failure = error;
  }

  if (isProductionServer(target)) {
    return {
      key: await importKeyOnce(CURRENT_SERVER_E2E_KEY.publicKeySpki),
      keyId: CURRENT_SERVER_E2E_KEY.keyId,
    };
  }
  throw failure === undefined
    ? new ServerE2eKeyUnavailableError(target, 'no-key')
    : new ServerE2eKeyUnavailableError(target, 'unreachable', { cause: failure });
}

/**
 * Fetch the E2E public key of the server at `serverUrl` (normalized) from its .well-known
 * endpoint. Resolves null when the server answers without a key; a fetch that fails rejects.
 */
async function discoverServerKey(
  serverUrl: string,
  pointer: AccountPointer
): Promise<{
  keyId: string;
  publicKeySpki: string;
} | null> {
  const known = discoveredKeys.get(serverUrl);
  if (known) {
    // The config may name this server only now (a login saved it after an earlier call discovered the key), so a remembered key is offered for saving too.
    await saveDiscoveredKey(serverUrl, known.publicKeySpki, pointer);
    return known;
  }

  const resp = await fetch(`${serverUrl}/account/api/v1/.well-known/server-info`, {
    signal: AbortSignal.timeout(5000),
  });
  if (!resp.ok) throw new Error(`server-info returned ${resp.status}`);
  const info = (await resp.json()) as {
    e2e?: { keys?: { keyId: string; publicKeySpki: string }[] };
  };
  const key = info.e2e?.keys?.[0];
  if (!key?.publicKeySpki) return null;
  discoveredKeys.set(serverUrl, key);

  await saveDiscoveredKey(serverUrl, key.publicKeySpki, pointer);
  return key;
}

/** True when `account` names `serverUrl` as its server and holds no key yet. */
function acceptsDiscoveredKey(
  account: { accountServer?: string; e2ePublicKey?: string } | undefined,
  serverUrl: string
): boolean {
  return (
    !account?.e2ePublicKey &&
    account?.accountServer !== undefined &&
    normalizeServerUrl(account.accountServer) === serverUrl
  );
}

/**
 * Servers whose discovered key needs no further save in this process: the save wrote it, the locked
 * config already held a key, or the write failed (the discovered key still serves this process).
 * A remembered key is then reused without taking the config lock again on every request.
 */
const keySaveSettled = new Set<string>();

/**
 * Save a discovered key into the active config, for the next startup: only when that config's
 * server IS the one the key came from and it holds no key yet, and that is checked again inside
 * the locked write. A check outside the lock alone let a discovery that started while `config
 * init` was still writing (its telemetry call resolves before the config names any server, so it
 * asks the production default) overwrite the key init had just saved with the production one;
 * every later request to the dev gateway then failed "Decryption failed" (reproduced 2026-10-21).
 * The key is device-local (DEVICE_LOCAL_POINTERS), so this writes this device's file even for a
 * remote config: no push, and so no pull re-entering this lookup. A failed save leaves the
 * discovered key in use for this process. `pointer` is the one the caller already read, so a
 * request reads the config once; a config that does not name this server yet is checked again on
 * the next request, since a login may name it later in the process.
 */
async function saveDiscoveredKey(
  serverUrl: string,
  publicKeySpki: string,
  pointer: AccountPointer
): Promise<void> {
  if (keySaveSettled.has(serverUrl)) return;
  // readAccountPointer stands `remote.apiUrl` in for a missing accountServer; only a saved accountServer owns a key.
  if (pointer.e2ePublicKey || pointer.accountServer === undefined) return;
  if (normalizeServerUrl(pointer.accountServer) !== serverUrl) return;
  // What the locked write found: `settled` when it wrote the key or a key was already there, `pending` when the config had come to name another server (checked again on a later request).
  let outcome: 'settled' | 'pending' = 'settled';
  try {
    await updateConfigAtPointer(getEffectiveConfigName(), '/account/e2ePublicKey', (cfg) => {
      if (acceptsDiscoveredKey(cfg.account, serverUrl)) {
        return { ...cfg, account: { ...(cfg.account ?? {}), e2ePublicKey: publicKeySpki } };
      }
      if (!cfg.account?.e2ePublicKey) outcome = 'pending';
      return cfg;
    });
  } catch {
    // The config may be gone or locked; the discovered key still serves this process.
  }
  if (outcome === 'settled') keySaveSettled.add(serverUrl);
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
  /** Test seam: the server's E2E key. Production passes nothing and getServerKeyMaterial(serverUrl) resolves it. */
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
  const { serverKey, keyId, send } = await tunnelTransport(options, serverUrl);
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

/** The server key and the fetch a tunnel request to `serverUrl` uses: the test seams when given, else that server's key. */
async function tunnelTransport(options: AccountFetchOptions, serverUrl: string) {
  const { key: serverKey, keyId } = options.serverKey ?? (await getServerKeyMaterial(serverUrl));
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
