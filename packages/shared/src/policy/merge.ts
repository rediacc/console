/**
 * The effective policy of a team config: the org policy as a ceiling, narrowed by the team policy
 * (agent/programs/remote-mcp/02-decisions.md D29, D30).
 *
 * A team policy only narrows. For each dimension the effective answer is "the org allows AND the
 * team allows": allow lists intersect, deny lists union (a deny at either side wins), the opt-in
 * switches AND, and an `allowGrandRepos` glob list combines as "an org glob matches AND a team glob
 * matches". Glob lists do not intersect into a glob list in general ("prod-*" and "*-eu" share
 * "prod-eu" and "prod-x-eu" but no single pattern), so the merge keeps both documents and decides
 * per request instead of folding them into one rule.
 *
 * A key the org policy locks (`locked`) is ignored wherever the team policy sets it, at every tier,
 * and reported in `ignoredLocked` so the editor can flag the row. A `locked` list inside the team
 * policy is ignored and reported as well: only the org policy locks.
 */

import {
  evaluatePolicy,
  narrowingDenial,
  type PolicyContext,
  type PolicyDecision,
} from './evaluate.js';
import type { PolicyDocument, PolicyRule, PolicyRuleKey } from './schema.js';

/** The org ceiling and the team narrowing of one config, as `mergePolicies` returns them. */
export interface EffectivePolicy {
  /** The org policy; absent when the org has none (the missing-policy default is the ceiling). */
  org?: PolicyDocument;
  /** The team policy as stored, locked keys included; absent for the org-level config. */
  team?: PolicyDocument;
  /** The keys the org locks, which evaluation ignores in the team policy. */
  locked: readonly PolicyRuleKey[];
  /**
   * Where the team policy set a locked key, as `<tier>.<key>`: `defaults.allowGrandRepos`,
   * `teams.<slug>.commands`, `users.<email>.repos`; and `locked` when the team policy carries its own
   * lock list.
   */
  ignoredLocked: string[];
}

function lockedKeysSet(rule: PolicyRule, locked: readonly PolicyRuleKey[]): PolicyRuleKey[] {
  return locked.filter((key) => rule[key] !== undefined);
}

function ignoredLockedRows(team: PolicyDocument, locked: readonly PolicyRuleKey[]): string[] {
  const rows: string[] = [];
  for (const key of lockedKeysSet(team.defaults, locked)) rows.push(`defaults.${key}`);
  for (const [slug, rule] of Object.entries(team.teams ?? {})) {
    for (const key of lockedKeysSet(rule, locked)) rows.push(`teams.${slug}.${key}`);
  }
  for (const [email, rule] of Object.entries(team.users ?? {})) {
    for (const key of lockedKeysSet(rule, locked)) rows.push(`users.${email}.${key}`);
  }
  if (team.locked !== undefined) rows.push('locked');
  return rows;
}

/**
 * Combine the org policy (the ceiling) with a team policy (the narrowing). Pass no team policy for
 * the org-level config.
 */
export function mergePolicies(org?: PolicyDocument, team?: PolicyDocument): EffectivePolicy {
  const locked = org?.locked ?? [];
  return {
    ...(org ? { org } : {}),
    ...(team ? { team } : {}),
    locked,
    ignoredLocked: team ? ignoredLockedRows(team, locked) : [],
  };
}

/**
 * Decide `ctx` against an effective policy: the org decision (`evaluatePolicy`, the missing-policy
 * default when the org has none) must allow, and the team policy must add no denial. With no org
 * policy a team policy cannot grant what the missing-policy default withholds: a team policy only
 * narrows.
 */
export function evaluateEffectivePolicy(
  effective: EffectivePolicy,
  ctx: PolicyContext
): PolicyDecision {
  const ceiling = evaluatePolicy(effective.org, ctx);
  if (!ceiling.allowed || !effective.team) return ceiling;
  return narrowingDenial(effective.team, ctx, new Set(effective.locked)) ?? ceiling;
}
