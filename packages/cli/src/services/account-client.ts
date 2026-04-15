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
import { t } from '../i18n/index.js';
import { ValidationError } from '../utils/errors.js';
import { getInstallMethod, getNpmUpdateCommand } from '../utils/platform.js';
import { VERSION } from '../version.js';
import {
  getSubscriptionServerUrl,
  getSubscriptionTokenState,
  loadServerConfig,
  normalizeServerUrl,
  saveServerConfig,
} from './subscription-auth.js';
import { resolveChannel } from './updater.js';

/** Cached server key material (imported once per process). */
let serverKeyCache: {
  key: Awaited<ReturnType<typeof importX25519PublicKey>>;
  keyId: string;
} | null = null;

export async function getServerKeyMaterial() {
  if (!serverKeyCache) {
    // 1. Explicit env var override (development mode)
    const envKey = process.env.X25519_PUBLIC_KEY;
    if (process.env.REDIACC_ENVIRONMENT === 'development' && envKey) {
      serverKeyCache = { key: await importX25519PublicKey(envKey), keyId: 'dev' };
      return serverKeyCache;
    }

    // 2. server.json (written by install script or `subscription login --server`)
    const serverConfig = loadServerConfig();
    if (serverConfig?.e2ePublicKey) {
      serverKeyCache = {
        key: await importX25519PublicKey(serverConfig.e2ePublicKey),
        keyId: 'discovered',
      };
      return serverKeyCache;
    }

    // 3. Runtime discovery from server's .well-known endpoint
    const discoveredKey = await discoverServerKey();
    if (discoveredKey) {
      serverKeyCache = {
        key: await importX25519PublicKey(discoveredKey.publicKeySpki),
        keyId: discoveredKey.keyId,
      };
      return serverKeyCache;
    }

    // 4. Hardcoded production key (fallback)
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

    // Cache in server.json for next startup
    const serverConfig = loadServerConfig();
    if (serverConfig && !serverConfig.e2ePublicKey) {
      saveServerConfig({ ...serverConfig, e2ePublicKey: key.publicKeySpki });
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
}

export interface AccountFetchError extends Error {
  status: number;
  code?: string;
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
  process.stderr.write(`\n${msg}\n\n`);
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
  const method = options.method ?? DEFAULT_HTTP_METHOD;

  // Resolve server URL
  const serverUrl = options.serverUrl ?? resolveServerUrl();

  // Build inner request headers
  const headers: Record<string, string> = {
    'x-cli-version': VERSION,
  };
  if (!options.noAuth) {
    const token = options.token ?? resolveStoredToken();
    headers['Authorization'] = `Bearer ${token}`;
  }
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }

  // Encrypt the request
  const { key: serverKey, keyId } = await getServerKeyMaterial();
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
  const resp = await fetch(tunnelUrl, {
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

  // Handle CLI upgrade required (426).
  // Pre-release builds (e.g. "0.0.0-dev") are developer artifacts — their
  // channel governs suitability, not the server's numeric min-version gate.
  // Swallow the 426 silently so callers treat it as a no-op instead of
  // printing a nonsensical "upgrade your dev build" banner.
  if (status === 426) {
    if (VERSION.includes('-')) {
      // Dev build: synthesize an empty result. `Object.create(null)` returns
      // `any` so it's assignable to an arbitrary generic T without an object
      // literal assertion. Callers' `.catch(() => null)` paths don't run.
      return Object.create(null);
    }
    handle426Response(
      parsed as {
        error?: string;
        minVersion?: string;
        currentVersion?: string;
        updateChannel?: string;
      },
      getInstallMethod()
    );
  }

  // Check the inner HTTP status
  if (status >= 400) {
    const msg = (parsed as { error?: string }).error ?? `Account server returned HTTP ${status}`;
    const code = (parsed as { code?: string }).code;
    throw createAccountError(msg, status, code);
  }

  return parsed;
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

function createAccountError(message: string, status: number, code?: string): AccountFetchError {
  const error = new Error(message) as AccountFetchError;
  error.status = status;
  if (code) error.code = code;
  return error;
}
