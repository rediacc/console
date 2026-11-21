/**
 * Stands in for `cloudflare:workers`, which exists only inside workerd, so every module that extends `WorkerEntrypoint` or `DurableObject` can load under vitest. Keeps `ctx` and `env` as the real classes do; a test that needs more mocks the module itself (vi.mock wins over this alias).
 */

export class WorkerEntrypoint {
  constructor(
    protected ctx: unknown,
    protected env: unknown
  ) {}
}

export class DurableObject {
  constructor(
    protected ctx: unknown,
    protected env: unknown
  ) {}
}
