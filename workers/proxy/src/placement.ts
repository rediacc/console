/**
 * Placement helpers (agent/plans/PLAN-org-executor-connect-timeout-relocate.md Design items 4 and 6).
 *
 * An org's executor is named by its placement, a number stored in D1. Moving the org to a fresh Durable Object means bumping that number, so the name changes and the old object is never touched again.
 */

/** Egress-unreachable reports within the window that make an org relocate. */
export const UNREACHABLE_THRESHOLD = 3;
/** How long a report counts, and how long `egressUnreachableAt` marks a pin answer as recent. */
export const UNREACHABLE_WINDOW_MS = 600_000;

/** The executor name: `<orgId>:p<placement>` for every placement, 0 included. It is the Durable Object name and the capacity lease key. */
export function executorName(orgId: string, placement: number): string {
  return `${orgId}:p${placement}`;
}

/** A placement from an untrusted value: a non-negative safe integer, else undefined. Never guesses 0, because 0 is the possibly broken object. */
export function placementOf(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : undefined;
}

/** True when a report at `at` (epoch ms) is still inside the window at `now`. A missing, future or non-finite `at` is not recent. */
export function unreachableRecent(at: number | undefined, now: number): boolean {
  if (typeof at !== 'number' || !Number.isFinite(at)) return false;
  const age = now - at;
  return age >= 0 && age < UNREACHABLE_WINDOW_MS;
}
