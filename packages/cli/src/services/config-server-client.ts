/**
 * Config Server Client
 *
 * Lightweight E2E-encrypted HTTP client for config storage API calls.
 * Uses X-Config-Token authentication instead of Bearer token.
 * Token rotation is handled transparently -- every response includes a new token.
 */

import {
  E2E_CONTENT_TYPE,
  type E2eResponseEnvelope,
  openResponse,
  sealRequest,
} from '@rediacc/shared/e2e';
import { getServerKeyMaterial } from './account-client.js';

export interface ConfigServerFetchOptions {
  /** HTTP method (default: GET) */
  method?: string;
  /** Request body (will be JSON-serialized) */
  body?: unknown;
  /** Rotating config token (X-Config-Token header) */
  configToken: string;
  /** Account server URL (e.g., 'https://account.rediacc.com') */
  serverUrl: string;
}

export interface ConfigServerResponse<T> {
  /** Parsed response body */
  data: T;
  /** Rotated token from the server (must be persisted immediately) */
  newServerToken?: string;
}

export class ConfigServerError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string
  ) {
    super(message);
    this.name = 'ConfigServerError';
  }
}

/** Default HTTP method for config server requests. */
const DEFAULT_HTTP_METHOD = 'GET';

/**
 * Send an E2E-encrypted request to the config storage API.
 *
 * Uses the same tunnel as accountServerFetch but with X-Config-Token
 * instead of Authorization header. Every response includes a rotated token.
 */
export async function configServerFetch<T = unknown>(
  path: string,
  options: ConfigServerFetchOptions
): Promise<ConfigServerResponse<T>> {
  const method = options.method ?? DEFAULT_HTTP_METHOD;

  // Build inner request headers with config token
  const headers: Record<string, string> = {
    'X-Config-Token': options.configToken,
  };
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }

  // Encrypt the request via E2E tunnel
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
  const tunnelUrl = `${options.serverUrl}/account/api/v1/tunnel`;
  const resp = await fetch(tunnelUrl, {
    method: 'POST',
    headers: { 'Content-Type': E2E_CONTENT_TYPE },
    body: JSON.stringify(envelope),
  });

  // Tunnel-level errors
  if (!resp.ok) {
    const errorBody = await resp.json().catch(() => ({ error: `HTTP ${resp.status}` }));
    const msg = (errorBody as { error?: string }).error ?? `HTTP ${resp.status}`;
    throw new ConfigServerError(msg, resp.status);
  }

  // Decrypt the response
  const responseEnvelope = (await resp.json()) as E2eResponseEnvelope;
  const { status, body } = await openResponse(aesKey, responseEnvelope);

  // Parse the decrypted response
  const parsed = (body ? JSON.parse(body) : {}) as T & {
    error?: string;
    code?: string;
    newServerToken?: string;
  };

  // Check the inner HTTP status
  if (status >= 400) {
    const msg = parsed.error ?? `Config server returned HTTP ${status}`;
    throw new ConfigServerError(msg, status, parsed.code);
  }

  return {
    data: parsed,
    newServerToken: parsed.newServerToken,
  };
}
