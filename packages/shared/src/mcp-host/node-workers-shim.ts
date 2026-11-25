/**
 * Lets Workers-targeted libraries load on Node unmodified.
 *
 * `@cloudflare/workers-oauth-provider` imports `WorkerEntrypoint` from the
 * `cloudflare:workers` built-in, which Node cannot resolve. A module resolve hook
 * maps that specifier to a small module carrying the one class the library uses
 * (it only checks `handler.prototype instanceof WorkerEntrypoint`), so the
 * library's own dist file runs as published.
 */
import { registerHooks } from 'node:module';

const WORKERS_SHIM_SOURCE = [
  'export class WorkerEntrypoint {',
  '  constructor(ctx, env) { this.ctx = ctx; this.env = env; }',
  '}',
].join('\n');

const WORKERS_SHIM_URL = `data:text/javascript,${encodeURIComponent(WORKERS_SHIM_SOURCE)}`;

let installed = false;

/** Installs the `cloudflare:workers` resolve hook once per process. */
export function installCloudflareWorkersShim(): void {
  if (installed) return;
  registerHooks({
    resolve(specifier, context, nextResolve) {
      if (specifier === 'cloudflare:workers') {
        return { url: WORKERS_SHIM_URL, format: 'module', shortCircuit: true };
      }
      return nextResolve(specifier, context);
    },
  });
  installed = true;
}

/** The part of the Workers `ExecutionContext` a Node host has to provide. */
export interface NodeExecutionContext {
  waitUntil(promise: Promise<unknown>): void;
  passThroughOnException(): void;
  props: Record<string, unknown>;
  /** Settles every promise handed to `waitUntil`; the Node host awaits it after a response. */
  drain(): Promise<void>;
}

export function createNodeExecutionContext(): NodeExecutionContext {
  const pending: Promise<unknown>[] = [];
  return {
    waitUntil(promise) {
      pending.push(promise);
    },
    passThroughOnException() {},
    props: {},
    async drain() {
      await Promise.allSettled(pending.splice(0));
    },
  };
}
