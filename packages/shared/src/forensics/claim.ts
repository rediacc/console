/**
 * The forensics licence claim (D9 of PLAN-forensics-shipping).
 *
 * `RepoLicense.forensics?: ForensicsClaim` is stamped at issue and renewal from
 * the plan entitlement and the repo's forensics settings. `enabled` is false on
 * an unpaid plan (the signer refuses an enabled claim there), `level` is what the
 * repo records now, and `maxLevel` is the most the customer may raise it to
 * (`full` on every paid plan). Levels are ordered, so comparing needs the rank
 * helpers here rather than string order.
 */
import { z } from 'zod';

/** The selectable capture levels of breach-forensics F2, lowest first; renet's netaudit.Level uses the same names. */
export const FORENSICS_LEVELS = ['basic', 'standard', 'full'] as const;
export type ForensicsLevel = (typeof FORENSICS_LEVELS)[number];

export const ForensicsLevelSchema = z.enum(FORENSICS_LEVELS);

/** Position of a level in the order basic < standard < full. */
export function levelRank(level: ForensicsLevel): number {
  return FORENSICS_LEVELS.indexOf(level);
}

export const ForensicsClaimSchema = z
  .strictObject({
    enabled: z.boolean(),
    level: ForensicsLevelSchema,
    maxLevel: ForensicsLevelSchema,
  })
  .refine((claim) => levelRank(claim.level) <= levelRank(claim.maxLevel), {
    path: ['level'],
    message: 'level may not exceed maxLevel',
  });
type ForensicsClaim = z.infer<typeof ForensicsClaimSchema>;

export type { ForensicsClaim };

/** The lower of two levels, for applying a quota-driven `levelCap` to a claim's level. */
export function clampLevel(level: ForensicsLevel, cap: ForensicsLevel): ForensicsLevel {
  return levelRank(level) <= levelRank(cap) ? level : cap;
}

/**
 * The level a repo records at: null when the claim is absent or disabled
 * (nothing is recorded), else the claim's level clamped to the session's cap.
 */
export function effectiveLevel(
  claim: ForensicsClaim | undefined,
  cap: ForensicsLevel = 'full'
): ForensicsLevel | null {
  if (!claim?.enabled) return null;
  return clampLevel(claim.level, cap);
}

/** True when a batch cut at `batchLevel` is within what the claim allows for the repo. */
export function levelWithinClaim(
  batchLevel: ForensicsLevel,
  claim: ForensicsClaim | undefined
): boolean {
  return claim?.enabled === true && levelRank(batchLevel) <= levelRank(claim.level);
}
