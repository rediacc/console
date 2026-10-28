/**
 * Per-org instance sizing for the `durable_object` backend (agent/plans/PLAN-executor-durable-object-policy.md Design item 4, box W4).
 *
 * The size is chosen at each container start, and a running container keeps its size until it stops (`OrgExecutor.pin` answers the running size). HEAVY is `standard-1`, for an org whose account route answers `tier: 'high'` (a BUSINESS or ENTERPRISE plan) or whose OrgExecutor recorded an out-of-memory exit within OOM_WINDOW_MS. LIGHT is everything else.
 *
 * Heavy slots are capped by the coordinator (src/capacity.ts `HARD_HEAVY_CAP`). When they are full, an org that is HEAVY only by its tier starts LIGHT, its size before this backend existed; an org that is HEAVY by an OOM exit is refused with `EXECUTOR_CAPACITY`, because LIGHT is known to fail it.
 */

import type { ExecutorSize } from './capacity';

/**
 * The instance each size class starts on. Each `instance:` value is a literal, which the cost guard (box G1) reads.
 *
 * LIGHT is the basic-equivalent custom size S1 chose (Spike record, DU3: `lite` would need a measured `machine status` peak below 200 MiB, and none exists). HEAVY is `standard-1`.
 */
export const INSTANCE_BY_SIZE = {
  light: { instance: { vcpu: 0.25, memoryMib: 1024, diskMb: 4000 } },
  heavy: { instance: 'standard-1' },
} as const satisfies Record<ExecutorSize, Pick<ContainerStartupOptions, 'instance'>>;

/** An out-of-memory exit flags the org HEAVY for this long after it happened. */
export const OOM_WINDOW_MS = 7 * 24 * 60 * 60 * 1000;

/** The account route's sizing tier. Anything but `high`, a missing field included, is `standard`. */
export type ExecutorTier = 'high' | 'standard';

/** Why a size was chosen: `oom` cannot fall back to LIGHT, `tier` can. */
export type SizeCause = 'oom' | 'tier' | 'none';

export interface SizeChoice {
  size: ExecutorSize;
  cause: SizeCause;
}

/** The tier a route answer names: only the exact string `high` counts. */
export function tierOf(value: unknown): ExecutorTier {
  return value === 'high' ? 'high' : 'standard';
}

/** Whether an OOM flag set at `oomAt` is still within OOM_WINDOW_MS of `now`. */
export function oomRecent(oomAt: number | undefined, now: number): boolean {
  return typeof oomAt === 'number' && Number.isFinite(oomAt) && now - oomAt <= OOM_WINDOW_MS;
}

/** The size to start on. An OOM flag outranks the tier, since only the tier may fall back to LIGHT. */
export function chooseSize(tier: ExecutorTier, oomAt: number | undefined, now: number): SizeChoice {
  if (oomRecent(oomAt, now)) return { size: 'heavy', cause: 'oom' };
  if (tier === 'high') return { size: 'heavy', cause: 'tier' };
  return { size: 'light', cause: 'none' };
}

/** The size to retry on when the heavy slots are full: LIGHT for an org that is HEAVY only by its tier, and none (a capacity refusal) for an OOM-flagged one. */
export function heavyFullFallback(choice: SizeChoice): ExecutorSize | undefined {
  return choice.size === 'heavy' && choice.cause === 'tier' ? 'light' : undefined;
}
