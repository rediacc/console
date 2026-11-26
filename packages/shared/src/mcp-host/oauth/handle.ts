/**
 * The `authRequest` handle (agent/plans/PLAN-rmcp-remote-worker.md Design 2): an opaque, HMAC-signed, single-use reference to a parsed authorization request kept in `OAUTH_KV`. The URL that carries it holds no secret and no request detail; a handle that was not signed with this Worker's key, or that was used or expired, resolves to nothing.
 *
 * Single use is a delete on `take`. KV has no compare-and-delete, so two concurrent `take` calls on one handle can both read it before either deletes; completing needs the grant's secret `S` as well, which bounds what a race gives.
 */
import type { AuthRequest } from '@cloudflare/workers-oauth-provider';

/** KV key prefix of the stored requests. */
export const AUTH_REQUEST_PREFIX = 'mcp-authreq:';

/** How long a request waits for the user to finish the portal page: KV's minimum is 60 s. */
export const AUTH_REQUEST_TTL_SECONDS = 600;

/** The KV calls the store makes. */
export interface HandleKv {
  get(key: string): Promise<string | null>;
  put(key: string, value: string, options?: { expirationTtl?: number }): Promise<void>;
  delete(key: string): Promise<void>;
}

/** A parsed authorization request and what the portal needs to know of it. */
export interface StoredAuthRequest {
  authRequest: AuthRequest;
  /** The grant id the client named in its `resource` parameter (`/g/<id>`), if it named one. */
  resourceGrantId?: string;
}

const encoder = new TextEncoder();

function base64url(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function fromBase64url(text: string): Uint8Array | null {
  // A base64 text of 1 mod 4 characters is never a whole number of bytes, and atob throws on it (review 32ad8b14.1).
  if (!/^[A-Za-z0-9_-]+$/.test(text) || text.length % 4 === 1) return null;
  const padded = text.replace(/-/g, '+').replace(/_/g, '/');
  return Uint8Array.from(atob(padded + '='.repeat((4 - (padded.length % 4)) % 4)), (c) =>
    c.charCodeAt(0)
  );
}

function hmacKey(secret: string, usage: 'sign' | 'verify'): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    [usage]
  );
}

async function sign(secret: string, id: string): Promise<string> {
  const mac = await crypto.subtle.sign(
    'HMAC',
    await hmacKey(secret, 'sign'),
    encoder.encode(`${AUTH_REQUEST_PREFIX}${id}`)
  );
  return base64url(new Uint8Array(mac));
}

/** The id of a handle whose signature verifies under `secret`, or null. */
async function verified(secret: string, handle: string): Promise<string | null> {
  const dot = handle.indexOf('.');
  if (dot < 1 || handle.length > 200) return null;
  const id = handle.slice(0, dot);
  const mac = fromBase64url(handle.slice(dot + 1));
  if (!mac || !/^[A-Za-z0-9_-]{16,64}$/.test(id)) return null;
  const ok = await crypto.subtle.verify(
    'HMAC',
    await hmacKey(secret, 'verify'),
    mac as BufferSource,
    encoder.encode(`${AUTH_REQUEST_PREFIX}${id}`)
  );
  return ok ? id : null;
}

export interface AuthRequestStore {
  /** Store a request and return its signed handle. */
  put(request: StoredAuthRequest): Promise<string>;
  /** Read a request without using it up (the portal page asks who is asking). */
  peek(handle: string): Promise<StoredAuthRequest | null>;
  /** Read a request and delete it. */
  take(handle: string): Promise<StoredAuthRequest | null>;
}

export function createAuthRequestStore(kv: HandleKv, secret: string): AuthRequestStore {
  async function read(handle: string): Promise<{ id: string; stored: StoredAuthRequest } | null> {
    const id = await verified(secret, handle);
    if (id === null) return null;
    const raw = await kv.get(`${AUTH_REQUEST_PREFIX}${id}`);
    return raw === null ? null : { id, stored: JSON.parse(raw) as StoredAuthRequest };
  }
  return {
    async put(request) {
      const id = base64url(crypto.getRandomValues(new Uint8Array(16)));
      await kv.put(`${AUTH_REQUEST_PREFIX}${id}`, JSON.stringify(request), {
        expirationTtl: AUTH_REQUEST_TTL_SECONDS,
      });
      return `${id}.${await sign(secret, id)}`;
    },
    async peek(handle) {
      return (await read(handle))?.stored ?? null;
    },
    async take(handle) {
      const found = await read(handle);
      if (!found) return null;
      await kv.delete(`${AUTH_REQUEST_PREFIX}${found.id}`);
      return found.stored;
    },
  };
}
