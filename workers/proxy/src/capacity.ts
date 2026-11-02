/**
 * `ExecutorCapacity`: the per-target coordinator that admits at most the cap of executor containers (agent/plans/PLAN-executor-durable-object-policy.md Design item 3).
 *
 * The `durable_object` scheduling policy does not support `max_instances`, so the cap moves into code. One instance per target (`idFromName(CAPACITY_NAME)`, reached only through `capacityStub`) holds one lease row per executor name (src/placement.ts `executorName`), so two placements of one org are two rows. A lease expires on its own after LEASE_MS, so a crashed or redeployed OrgExecutor frees its slot with no cleanup path, and the alarm sweeps what nobody renewed.
 *
 * Every decision runs on the synchronous SQLite API with no `await` between the read that counts the holders and the write that admits one, so concurrent `acquire` calls cannot interleave inside a decision and never admit more than the cap.
 */

import { DurableObject } from 'cloudflare:workers';

/** The ceiling no `EXECUTOR_CAP` can raise. The cost guard reads this literal, so it stays an integer literal. */
export const HARD_CAP = 25;
/** The ceiling no `EXECUTOR_HEAVY_CAP` can raise (Decisions 3). The cost guard reads this literal, so it stays an integer literal. */
export const HARD_HEAVY_CAP = 5;
/** A lease's life: OrgExecutor's `sleepAfter` of 120 s plus 60 s of grace for a renew in flight. */
export const LEASE_MS = 180_000;
/**
 * The name of the one coordinator instance per target. The suffix versions the table shape: v2 keys leases by executor name, not by org.
 *
 * A new suffix starts an EMPTY instance, so for at most LEASE_MS after the deploy that introduces it the cap does not see executors still holding a lease on the old instance: the running total can exceed the cap by the old holders, at most the old cap itself (review 872e964a.1). Each such executor moves over at its first renew (`renew` on the new instance answers `not-held`, and OrgExecutor acquires again there, src/org-executor.ts `holdLease`), and an idle one stops at `sleepAfter`, so the overshoot is one-time and bounded by LEASE_MS. It was accepted for the v1-to-v2 cutover; a future suffix change carries the same transient and should be deployed when the target is quiet.
 */
export const CAPACITY_NAME = 'capacity:v2';

/** The instance size class a lease is counted under. `heavy` leases also count against the heavy sub-cap. */
export type ExecutorSize = 'light' | 'heavy';

/** The answer to `acquire`. `full` is the target cap, `heavy-full` the heavy sub-cap. */
export type AcquireAnswer = { ok: true } | { ok: false; reason: 'full' | 'heavy-full' };

/** The answer to `renew`. `not-held` means the slot may already be someone else's, so the caller acquires again. */
export type RenewAnswer = 'held' | 'not-held';

/** The live holders and the limits in force, read only. */
export interface CapacityCount {
  total: number;
  heavy: number;
  cap: number;
  heavyCap: number;
}

/** The vars the coordinator reads. Both are decimal strings generated per target by proxy_configs.py. */
export interface CapacityEnv {
  EXECUTOR_CAP?: string;
  EXECUTOR_HEAVY_CAP?: string;
}

/**
 * A configured cap, never above `hard`. Only a plain decimal string counts: `parseInt` alone would read `"2abc"` as 2 and `"-1"` as a negative cap, and a missing or garbage value must mean the hard cap, never unlimited and never a guess.
 */
export function capFrom(value: string | undefined, hard: number): number {
  if (value === undefined || !/^\d+$/.test(value)) return hard;
  return Math.min(Number.parseInt(value, 10), hard);
}

/** The stub of the target's one coordinator instance, so every caller names the same instance. */
export function capacityStub(
  namespace: DurableObjectNamespace<ExecutorCapacity>
): DurableObjectStub<ExecutorCapacity> {
  return namespace.get(namespace.idFromName(CAPACITY_NAME));
}

function isSize(size: unknown): size is ExecutorSize {
  return size === 'light' || size === 'heavy';
}

/** The coordinator Durable Object. See the module comment for why it exists and why its decisions cannot race. */
export class ExecutorCapacity extends DurableObject<CapacityEnv> {
  private readonly sql: SqlStorage;
  private readonly cap: number;
  private readonly heavyCap: number;

  constructor(ctx: DurableObjectState, env: CapacityEnv) {
    super(ctx, env);
    this.sql = ctx.storage.sql;
    this.cap = capFrom(env.EXECUTOR_CAP, HARD_CAP);
    this.heavyCap = capFrom(env.EXECUTOR_HEAVY_CAP, HARD_HEAVY_CAP);
    this.sql.exec(
      'CREATE TABLE IF NOT EXISTS leases (executor TEXT PRIMARY KEY, size TEXT NOT NULL, expires_at INTEGER NOT NULL)'
    );
  }

  /**
   * Take or renew the executor's slot for LEASE_MS. Idempotent per executor: a held executor renews and is never counted twice, and it keeps its slot even when a lowered cap now sits below the holder count, because its container is already running. A held light org asking for heavy is refused `heavy-full` when the heavy slots are taken, and keeps its light lease.
   */
  async acquire(executor: string, size: ExecutorSize): Promise<AcquireAnswer> {
    if (typeof executor !== 'string' || executor === '')
      throw new TypeError('acquire: executor required');
    // An unknown size would otherwise slip past the heavy sub-cap, so it is refused rather than counted as light.
    if (!isSize(size)) throw new TypeError('acquire: size must be light or heavy');

    const now = Date.now();
    this.sweep(now);
    const held = this.sql
      .exec<{ size: string }>('SELECT size FROM leases WHERE executor = ?', executor)
      .toArray()[0];
    const { total, heavy } = this.tally(now);

    if (held === undefined && total >= this.cap) return { ok: false, reason: 'full' };
    // A held heavy executor keeps its heavy slot under a lowered heavy cap, as a held executor keeps its slot under a lowered cap: its container already runs.
    if (size === 'heavy' && held?.size !== 'heavy' && heavy >= this.heavyCap) {
      return { ok: false, reason: 'heavy-full' };
    }

    this.sql.exec(
      'INSERT INTO leases (executor, size, expires_at) VALUES (?, ?, ?) ON CONFLICT(executor) DO UPDATE SET size = excluded.size, expires_at = excluded.expires_at',
      executor,
      size,
      now + LEASE_MS
    );
    // The admission is already written, so a call that runs while this awaits sees it counted.
    await this.scheduleSweep();
    return { ok: true };
  }

  /** Extend a live lease by LEASE_MS. An expired lease is dropped rather than revived, because its slot may have been handed out at the last sweep. */
  async renew(executor: string): Promise<RenewAnswer> {
    const now = Date.now();
    const held = this.sql
      .exec<{ expires_at: number }>('SELECT expires_at FROM leases WHERE executor = ?', executor)
      .toArray()[0];
    if (held === undefined) return 'not-held';
    if (held.expires_at <= now) {
      this.sql.exec('DELETE FROM leases WHERE executor = ?', executor);
      await this.scheduleSweep();
      return 'not-held';
    }
    this.sql.exec('UPDATE leases SET expires_at = ? WHERE executor = ?', now + LEASE_MS, executor);
    await this.scheduleSweep();
    return 'held';
  }

  /** Give the executor's slot back. Releasing a slot not held is a no-op, so an idle teardown racing an expiry needs no guard. */
  async release(executor: string): Promise<void> {
    this.sql.exec('DELETE FROM leases WHERE executor = ?', executor);
    await this.scheduleSweep();
  }

  /** The live holders and the limits, for `/v1/ready` and tests. Read only: expired rows are skipped, not deleted. Synchronous here; an RPC caller still awaits it. */
  count(): CapacityCount {
    return { ...this.tally(Date.now()), cap: this.cap, heavyCap: this.heavyCap };
  }

  /** Sweep what expired and re-arm for the next expiry, so a slot frees even when no acquire arrives. */
  override async alarm(): Promise<void> {
    this.sweep(Date.now());
    await this.scheduleSweep();
  }

  private sweep(now: number): void {
    this.sql.exec('DELETE FROM leases WHERE expires_at <= ?', now);
  }

  private tally(now: number): { total: number; heavy: number } {
    const row = this.sql
      .exec<{ total: number; heavy: number | null }>(
        "SELECT COUNT(*) AS total, SUM(CASE WHEN size = 'heavy' THEN 1 ELSE 0 END) AS heavy FROM leases WHERE expires_at > ?",
        now
      )
      .one();
    return { total: row.total, heavy: row.heavy ?? 0 };
  }

  /**
   * Arm the alarm at the earliest expiry, or clear it when nothing is held, so an empty coordinator costs no wake-ups.
   *
   * A failure to set the alarm is logged, not thrown: the lease is already written, so throwing would report a refusal for a slot that is held, and a lapsed lease stops counting at its expiry whatever the alarm does (tally reads only live rows), so a missed alarm leaves only stale rows for the next sweep.
   */
  private async scheduleSweep(): Promise<void> {
    const next = this.sql
      .exec<{ next: number | null }>('SELECT MIN(expires_at) AS next FROM leases')
      .one().next;
    try {
      if (next === null) await this.ctx.storage.deleteAlarm();
      else await this.ctx.storage.setAlarm(next);
    } catch (error) {
      console.warn(
        `proxy: capacity alarm not set: ${error instanceof Error ? error.name : 'unknown'}`
      );
    }
  }
}
