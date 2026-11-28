/**
 * Per-grant rate limits and one-time nonces (agent/plans/PLAN-rmcp-remote-worker.md Design 6 and 8).
 *
 * One limiter instance per grant enforces a strict budget: RATE_CALLS_PER_MINUTE `tools/call` in any sliding minute and RATE_MAX_CONCURRENT calls in flight. A call over either budget is refused with `REDIACC_RATE_LIMITED` and a retry hint. The same instance burns confirmation nonces, so a sealed `requestState` is accepted once.
 *
 * `GrantLimiter` is the state machine and runs anywhere. `GrantRateObject` hosts one in a Durable Object (the `RATE` binding, one object per grant name), so every isolate of a region shares the budget; `doRateLimiter` is the Worker's client for it, and `MemoryRateLimiter` serves tests and a Worker deployed without the binding (per isolate only).
 *
 * A call that never reports back (an isolate killed mid-call) holds its concurrency slot until SLOT_LEASE_MS passes, so a crash cannot lock a grant out.
 */

export const RATE_CALLS_PER_MINUTE = 60;
export const RATE_MAX_CONCURRENT = 5;
export const RATE_WINDOW_MS = 60_000;

/** A slot not released within this long is taken as lost: the call window plus a margin. */
export const SLOT_LEASE_MS = 60_000;

export type Acquired =
  | { ok: true; release: () => Promise<void> }
  | { ok: false; reason: 'calls' | 'concurrent'; retryAfterSeconds: number };

/** What `callTool` needs of a limiter: a slot per call, and a one-time burn per confirmation nonce. */
export interface RateLimiter {
  acquire(grantId: string): Promise<Acquired>;
  /** True the first time `nonce` is burned for `grantId` and false afterwards, until `expiresAt` (epoch ms) passes. */
  burn(grantId: string, nonce: string, expiresAt: number): Promise<boolean>;
}

/** The counters of one grant. */
export class GrantLimiter {
  private readonly calls: number[] = [];
  private readonly slots = new Map<string, number>();
  private readonly nonces = new Map<string, number>();
  private seq = 0;

  constructor(private readonly now: () => number = Date.now) {}

  /** Take a slot, or learn how long to wait. */
  acquire():
    | { ok: true; slot: string }
    | { ok: false; reason: 'calls' | 'concurrent'; retryAfterSeconds: number } {
    const t = this.now();
    while (this.calls.length > 0 && this.calls[0] <= t - RATE_WINDOW_MS) this.calls.shift();
    for (const [slot, since] of this.slots) if (since <= t - SLOT_LEASE_MS) this.slots.delete(slot);
    if (this.calls.length >= RATE_CALLS_PER_MINUTE) {
      const wait = this.calls[0] + RATE_WINDOW_MS - t;
      return { ok: false, reason: 'calls', retryAfterSeconds: Math.max(1, Math.ceil(wait / 1000)) };
    }
    if (this.slots.size >= RATE_MAX_CONCURRENT) {
      return { ok: false, reason: 'concurrent', retryAfterSeconds: 1 };
    }
    this.seq += 1;
    const slot = String(this.seq);
    this.calls.push(t);
    this.slots.set(slot, t);
    return { ok: true, slot };
  }

  release(slot: string): void {
    this.slots.delete(slot);
  }

  burn(nonce: string, expiresAt: number): boolean {
    const t = this.now();
    for (const [n, exp] of this.nonces) if (exp <= t) this.nonces.delete(n);
    if (this.nonces.has(nonce)) return false;
    this.nonces.set(nonce, expiresAt);
    return true;
  }
}

/** Limiters held in this isolate's memory, one per grant. */
export class MemoryRateLimiter implements RateLimiter {
  private readonly byGrant = new Map<string, GrantLimiter>();

  constructor(private readonly now: () => number = Date.now) {}

  private limiter(grantId: string): GrantLimiter {
    let limiter = this.byGrant.get(grantId);
    if (!limiter) {
      limiter = new GrantLimiter(this.now);
      this.byGrant.set(grantId, limiter);
    }
    return limiter;
  }

  acquire(grantId: string): Promise<Acquired> {
    const limiter = this.limiter(grantId);
    const taken = limiter.acquire();
    if (!taken.ok) return Promise.resolve(taken);
    return Promise.resolve({
      ok: true,
      release: () => {
        limiter.release(taken.slot);
        return Promise.resolve();
      },
    });
  }

  burn(grantId: string, nonce: string, expiresAt: number): Promise<boolean> {
    return Promise.resolve(this.limiter(grantId).burn(nonce, expiresAt));
  }
}

/** The part of `DurableObjectState` the object reads. */
interface ObjectState {
  storage: {
    get<T>(key: string): Promise<T | undefined>;
    put(key: string, value: unknown): Promise<void>;
  };
}

type RateRequest =
  | { op: 'acquire' }
  | { op: 'release'; slot: string }
  | { op: 'burn'; nonce: string; expiresAt: number };

/**
 * The `RATE` Durable Object: one instance per grant, holding a GrantLimiter. The counters stay in memory (a call budget and a slot count need no durability), and the burned nonces are written to storage so a state stays burned across an eviction.
 */
export class GrantRateObject {
  private readonly limiter = new GrantLimiter();
  private nonces: Promise<void> | undefined;

  constructor(private readonly state: ObjectState) {}

  /** The nonces burned before this instance started, read once from storage. */
  private async loadNonces(): Promise<void> {
    const stored = (await this.state.storage.get<[string, number][]>('nonces')) ?? [];
    for (const [nonce, expiresAt] of stored) this.limiter.burn(nonce, expiresAt);
  }

  async fetch(request: Request): Promise<Response> {
    const body = (await request.json()) as RateRequest;
    if (body.op === 'acquire') return Response.json(this.limiter.acquire());
    if (body.op === 'release') {
      this.limiter.release(body.slot);
      return Response.json({ ok: true });
    }
    await (this.nonces ??= this.loadNonces());
    const fresh = this.limiter.burn(body.nonce, body.expiresAt);
    if (fresh) {
      const kept = ((await this.state.storage.get<[string, number][]>('nonces')) ?? []).filter(
        ([, exp]) => exp > Date.now()
      );
      kept.push([body.nonce, body.expiresAt]);
      await this.state.storage.put('nonces', kept);
    }
    return Response.json({ fresh });
  }
}

/** The part of a Durable Object namespace the client uses. */
export interface RateNamespace {
  idFromName(name: string): unknown;
  get(id: unknown): { fetch(request: Request): Promise<Response> };
}

/** A limiter whose state lives in the `RATE` Durable Object of each grant. */
export function doRateLimiter(namespace: RateNamespace): RateLimiter {
  const send = async (grantId: string, body: RateRequest): Promise<unknown> => {
    const stub = namespace.get(namespace.idFromName(grantId));
    const response = await stub.fetch(
      new Request('https://rate.internal/', { method: 'POST', body: JSON.stringify(body) })
    );
    return response.json();
  };
  return {
    async acquire(grantId) {
      const answer = (await send(grantId, { op: 'acquire' })) as
        | { ok: true; slot: string }
        | { ok: false; reason: 'calls' | 'concurrent'; retryAfterSeconds: number };
      if (!answer.ok) return answer;
      return {
        ok: true,
        release: async () => {
          await send(grantId, { op: 'release', slot: answer.slot });
        },
      };
    },
    async burn(grantId, nonce, expiresAt) {
      return ((await send(grantId, { op: 'burn', nonce, expiresAt })) as { fresh: boolean }).fresh;
    },
  };
}
