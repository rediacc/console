/**
 * The runtime's active span, shared by the Worker's fetch handler (src/index.ts) and the `AccountEgress` entrypoint (src/egress.ts).
 *
 * Workers Observability exports the span to the `destinations` in wrangler.toml. Attributes carry identity only: never a token, org id, team id or tenant key.
 */

/** The slice of the Workers runtime `Span` the proxy uses (the account Worker's middleware/tracing.ts declares the same). */
export interface RuntimeSpan {
  setAttribute(key: string, value: boolean | number | string): unknown;
}

interface RuntimeTracing {
  getActiveSpan(): RuntimeSpan | undefined;
}

/** The active span of an execution context (a fetch handler's `ctx` or an entrypoint's `this.ctx`); undefined when the host supplies no tracing (tests, wrangler dev without it). */
export function activeSpan(ctx: unknown): RuntimeSpan | undefined {
  try {
    return (ctx as { tracing?: RuntimeTracing } | undefined)?.tracing?.getActiveSpan?.();
  } catch {
    return undefined;
  }
}
