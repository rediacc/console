/**
 * The two Workers runtime types the handler names, declared structurally so the module compiles under `@rediacc/shared`'s own tsconfig (no `@cloudflare/workers-types`) and on Node. Cloudflare's `KVNamespace` and `ExecutionContext`, the SQLite KV adapter and the Node execution context all satisfy them.
 */

/** The part of the Workers `ExecutionContext` the handler and the OAuth provider call. */
export interface HostExecutionContext {
  waitUntil(promise: Promise<unknown>): void;
  passThroughOnException(): void;
}

/** The part of the Workers KV binding the OAuth provider and the handle store call. */
export interface HostKvNamespace {
  get(key: string): Promise<string | null>;
  get(key: string, type: 'text'): Promise<string | null>;
  get(key: string, type: 'json'): Promise<unknown>;
  put(
    key: string,
    value: string,
    options?: { expirationTtl?: number; expiration?: number }
  ): Promise<void>;
  delete(key: string): Promise<void>;
  list(options?: { prefix?: string; cursor?: string; limit?: number }): Promise<unknown>;
}
