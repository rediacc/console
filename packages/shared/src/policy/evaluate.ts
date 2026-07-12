/**
 * Policy evaluation.
 *
 * One function, called by both the executor (to decide) and the permissions UI
 * (to preview). Keeping a single implementation is the point: a rule that reads
 * as "allowed" in the console must be the rule the executor enforces.
 */

import type { MutationScope, PolicyDocument, PolicyOrgRole, PolicyRule } from './schema.js';

/**
 * What happens when an organization has NO policy document at all.
 *
 * Locked decision: owners and admins may act, plain members may not. A missing
 * document means "nobody has granted members anything yet", not "everything is
 * permitted" — an org that has never opened the permissions page must not be
 * silently wide open to every member.
 *
 * Exported so the executor and the permissions UI agree on the empty state
 * instead of each hard-coding its own guess.
 */
export const MISSING_POLICY_DEFAULT: Readonly<Record<PolicyOrgRole, boolean>> = Object.freeze({
  owner: true,
  admin: true,
  member: false,
});

export interface PolicyContext {
  /** Key into `users`. */
  userEmail: string;
  /** Key into `teams`. Absent when the caller belongs to no team. */
  teamSlug?: string;
  orgRole: PolicyOrgRole;
  /** Space-separated command path, e.g. "repo fork". See schema.ts. */
  commandPath: string;
  /** Target machine, when the command has one. */
  machineName?: string;
  /** Target repo, when the command has one. */
  repoName?: string;
  /**
   * The command destroys or discards data (repo delete, cluster destroy).
   *
   * Version 1 of the policy language has no dedicated destructive gate: a
   * destructive command is restricted like any other, via `commands.deny` or by
   * omission from `commands.allow`. The flag is carried into the decision reason
   * so the CLI error and the audit trail both record that the command under
   * consideration was destructive.
   */
  destructive?: boolean;
  /** Target repo is a grand (root) repo. Gated by `allowGrandRepos`. */
  isGrandRepo?: boolean;
  /**
   * Command is a cluster lifecycle operation, gated by `allowClusterOps`. When
   * omitted it is derived from the command path (a leading "cluster" or "kube"
   * segment), so a caller with no better signal still gets the gate.
   */
  isClusterOp?: boolean;
  /** Mutation class this command performs. Gated by `mutationScopes`. */
  mutationScope?: MutationScope;
}

export interface PolicyDecision {
  allowed: boolean;
  /** Human-readable justification, safe to show in a CLI error or the console. */
  reason: string;
}

/**
 * Match one glob against a whole value. `*` spans any run of characters,
 * including spaces, so "repo *" reaches "repo secret set". Everything else is
 * literal.
 */
export function matchesGlob(pattern: string, value: string): boolean {
  // Split on the wildcard first, then escape each literal chunk. Escaping the
  // pattern in a single pass would force the segment-separating spaces to double
  // as the wildcard sentinel, which makes the exact pattern "repo fork" match
  // "repoXXXfork".
  const source = pattern
    .split('*')
    .map((literal) => literal.replace(/[.+?^${}()|[\]\\]/g, '\\$&'))
    .join('.*');
  return new RegExp(`^${source}$`).test(value);
}

const matchesAny = (patterns: readonly string[], value: string): boolean =>
  patterns.some((pattern) => matchesGlob(pattern, value));

/**
 * Tiers that apply to this caller, least specific first:
 * defaults -> team -> user, so the last entry is the most specific.
 */
function applicableTiers(doc: PolicyDocument, ctx: PolicyContext): PolicyRule[] {
  const tiers: PolicyRule[] = [doc.defaults];
  const team = ctx.teamSlug ? doc.teams?.[ctx.teamSlug] : undefined;
  if (team) tiers.push(team);
  const user = doc.users?.[ctx.userEmail];
  if (user) tiers.push(user);
  return tiers;
}

/**
 * One dimension's value, taken from the most specific tier that defines it. A
 * tier that omits a field does not override a broader tier that set it, which is
 * what lets a user rule refine a single dimension without restating the rest.
 */
function resolve<K extends keyof PolicyRule>(
  tiers: readonly PolicyRule[],
  key: K
): PolicyRule[K] | undefined {
  for (let i = tiers.length - 1; i >= 0; i--) {
    const value = tiers[i][key];
    if (value !== undefined) return value;
  }
  return undefined;
}

/** A leading "cluster"/"kube" segment marks a cluster lifecycle op. */
function looksLikeClusterOp(commandPath: string): boolean {
  const head = commandPath.trim().split(/\s+/)[0];
  return head === 'cluster' || head === 'kube';
}

/**
 * Decide whether `ctx` is permitted by `doc`.
 *
 * Precedence is user > team > defaults, resolved per dimension. An explicit
 * `commands.deny` match wins at ANY tier: a deny written into the org defaults
 * cannot be undone by a more specific user rule, so a blanket ban stays a ban.
 */
export function evaluatePolicy(
  doc: PolicyDocument | undefined,
  ctx: PolicyContext
): PolicyDecision {
  const subject = ctx.destructive
    ? `destructive command "${ctx.commandPath}"`
    : `"${ctx.commandPath}"`;

  if (!doc) {
    const allowed = MISSING_POLICY_DEFAULT[ctx.orgRole];
    return {
      allowed,
      reason: allowed
        ? `No policy is configured; ${ctx.orgRole}s may run ${subject} by default.`
        : `No policy is configured; ${ctx.orgRole}s may not run ${subject}. An owner or admin must grant access.`,
    };
  }

  const tiers = applicableTiers(doc, ctx);

  // Deny outranks everything, at every tier.
  for (const tier of tiers) {
    const deny = tier.commands?.deny;
    if (deny && matchesAny(deny, ctx.commandPath)) {
      return { allowed: false, reason: `Policy explicitly denies ${subject}.` };
    }
  }

  // Commands are an ALLOW-LIST, and the list is required. A document that
  // resolves NO commands rule for this caller allows nothing — it does not allow
  // everything. This is the one place the model must fail closed: a rule that
  // scopes, say, `machines` but forgets `commands` would otherwise silently
  // grant every command (repo secret get, cluster destroy) on those machines.
  // An author who genuinely wants everything writes `commands: { allow: ['*'] }`.
  const commands = resolve(tiers, 'commands');
  if (!commands) {
    return {
      allowed: false,
      reason: `Policy allow-lists no commands for ${subject}. Add a commands.allow rule (use ['*'] to permit all).`,
    };
  }
  if (!matchesAny(commands.allow, ctx.commandPath)) {
    return { allowed: false, reason: `Policy does not allow ${subject}.` };
  }

  const machines = resolve(tiers, 'machines');
  if (ctx.machineName && machines && !matchesAny(machines, ctx.machineName)) {
    return { allowed: false, reason: `Policy does not allow machine "${ctx.machineName}".` };
  }

  const repos = resolve(tiers, 'repos');
  if (ctx.repoName && repos && !matchesAny(repos, ctx.repoName)) {
    return { allowed: false, reason: `Policy does not allow repo "${ctx.repoName}".` };
  }

  if (ctx.isGrandRepo && resolve(tiers, 'allowGrandRepos') !== true) {
    return {
      allowed: false,
      reason: `Policy does not allow operations on grand repos ("${ctx.repoName ?? 'unknown'}").`,
    };
  }

  const isClusterOp = ctx.isClusterOp ?? looksLikeClusterOp(ctx.commandPath);
  if (isClusterOp && resolve(tiers, 'allowClusterOps') !== true) {
    return { allowed: false, reason: 'Policy does not allow cluster operations.' };
  }

  const mutationScopes = resolve(tiers, 'mutationScopes');
  if (ctx.mutationScope && mutationScopes && !mutationScopes.includes(ctx.mutationScope)) {
    return { allowed: false, reason: `Policy does not allow "${ctx.mutationScope}" mutations.` };
  }

  return { allowed: true, reason: `Policy allows ${subject}.` };
}
