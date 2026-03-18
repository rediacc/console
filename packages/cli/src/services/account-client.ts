/**
 * Account Server Client
 *
 * Centralized HTTP client for all CLI → account server communication.
 * All requests are E2E encrypted via X25519 ECDH + AES-256-GCM tunnel.
 */

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
import { getSubscriptionServerUrl, getSubscriptionTokenState } from './subscription-auth.js';

/** Cached server key material (imported once per process). */
let serverKeyCache: {
  key: Awaited<ReturnType<typeof importX25519PublicKey>>;
  keyId: string;
} | null = null;

async function getServerKeyMaterial() {
  if (!serverKeyCache) {
    const envKey = process.env.X25519_PUBLIC_KEY;
    if (process.env.REDIACC_ENVIRONMENT === 'development' && envKey) {
      serverKeyCache = { key: await importX25519PublicKey(envKey), keyId: 'dev' };
    } else {
      serverKeyCache = {
        key: await importX25519PublicKey(CURRENT_SERVER_E2E_KEY.publicKeySpki),
        keyId: CURRENT_SERVER_E2E_KEY.keyId,
      };
    }
  }
  return serverKeyCache;
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
  const headers: Record<string, string> = {};
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
