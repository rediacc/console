/**
 * The one decision function (agent/plans/PLAN-rmcp-decide.md, decisions D18-D24).
 *
 * Every path that runs an `rdc` command (the CLI, the local MCP server, the remote MCP Worker,
 * `rdc --proxy`, the web console) builds a `DecisionContext` and asks `decide` for one answer.
 * The function is pure: no I/O, no clock, no environment. Resolving the target repo, reading the
 * policy record and proving that an override was set by a human all happen in the caller's
 * adapters, which hand the results in as plain data.
 *
 * Rules, in order (the first refusal wins):
 *
 * 1. The policy decides the command itself (`commands` allow/deny, machine and repo scopes,
 *    mutation scopes). A `null` policy falls back to `MISSING_POLICY_DEFAULT` by org role.
 * 2. An agent may never run an `agentBlocked` command outside the cluster family.
 * 3. An agent may not run a `forkBlocked` command on a fork.
 * 4. A cluster or datastore lifecycle operation needs the policy's `allowClusterOps`, and an agent
 *    additionally needs a cluster opt-in naming the subject (D22: opt-in AND ceiling).
 * 5. A `grandGuard` command on a grand target needs the policy's `allowGrandRepos`, and an agent
 *    additionally needs a grand-repo opt-in naming the repo. An unresolved or absent repo counts
 *    as grand (fail closed); `repo promote` always lands on the grand. An ops-VM placement skips
 *    this rule, and only this rule.
 * 6. An agent cleared by rule 5 for a destructive command gets `needs_confirmation` until the
 *    caller retries with `confirmation.granted`.
 *
 * Dispatchability (whether the command exists and may be dispatched at all) stays the caller's
 * first check and never reaches this function.
 */

import { POLICY_DEFAULTS } from '../config/defaults.js';
import type { DecisionCode, DecisionVerdict } from './decision-codes.js';
import type { PolicyContext } from './evaluate.js';
import type { EffectivePolicy } from './merge.js';
import { evaluateEffectivePolicy } from './merge.js';
import type { MutationScope, PolicyOrgRole } from './schema.js';

/** Who asks. An agent is any caller acting without a human at the keyboard. */
export interface DecisionPrincipal {
  kind: 'human' | 'agent';
  userEmail: string;
  orgRole: PolicyOrgRole;
  /** The team the caller acts under, used to pick the team tier of the policy. */
  teamSlug?: string;
}

/** The fields of a CLI contract entry the decision reads. */
export interface DecisionCommand {
  /** Space-separated command path, e.g. "repo up". */
  pathKey: string;
  destructive?: boolean;
  /** The command changes the repo it names, so a grand target needs an opt-in. */
  grandGuard?: boolean;
  /** The command does not apply to a fork. */
  forkBlocked?: boolean;
  /** The command is withheld from agents (the cluster family can be opted into). */
  agentBlocked?: boolean;
  /** Mutation class the command performs, for the policy's `mutationScopes`. */
  mutationScope?: MutationScope;
}

/** Whether the named repo is a grand, a fork, or could not be identified. */
export type RepoState = 'grand' | 'fork' | 'unresolved';

export interface DecisionTarget {
  machine?: string;
  /**
   * The repo the command lands on. For a command in `MUTATES_GRAND_BY_DEFINITION` (`repo promote`)
   * that is the grand the fork replaces, so the caller names the grand here.
   */
  repo?: { name: string; state: RepoState };
  /**
   * The name a cluster opt-in must cover: the cluster name for `cluster <verb>`, the datastore
   * name for `datastore <verb>`. Absent when the command names none, which only a `*` opt-in covers.
   */
  subject?: string;
  /** The target sits on the development-only ops VM fleet, which the grand-repo rule never blocks. */
  isOpsVm: boolean;
}

/**
 * A human-set session opt-in. Locally it comes from the ancestry-verified environment variables
 * (`source: 'env'`); remotely from the agent grant row (`source: 'grant'`). A list names repos or
 * subjects exactly (case-sensitive); `'*'` covers every one; `null` grants nothing.
 */
export interface DecisionOverrides {
  grandRepos: readonly string[] | '*' | null;
  clusterOps: readonly string[] | '*' | null;
  source: 'env' | 'grant' | 'none';
}

export interface DecisionContext {
  principal: DecisionPrincipal;
  command: DecisionCommand;
  target: DecisionTarget;
  /** The effective policy (merge.ts), or `null` when the org has none. */
  policy: EffectivePolicy | null;
  overrides: DecisionOverrides;
  /** Set on the retry after a `needs_confirmation` answer was confirmed. */
  confirmation: { granted: boolean };
}

export interface DecisionNext {
  /** A command that gets the caller past the refusal, e.g. forking the grand repo first. */
  run?: string;
  /** The argument and value a retry carries to confirm a `needs_confirmation` answer. */
  confirm?: { argument: 'confirm'; value: string };
}

export interface Decision {
  verdict: DecisionVerdict;
  code: DecisionCode;
  /** English justification; surfaces translate by `code` and may show this as detail. */
  reason: string;
  next?: DecisionNext;
}

/** Commands whose effect lands on the grand repo whatever their ref names. */
export const MUTATES_GRAND_BY_DEFINITION: ReadonlySet<string> = new Set(['repo promote']);

/** Command families whose `agentBlocked` verbs a cluster opt-in can unlock. */
const CLUSTER_FAMILIES: ReadonlySet<string> = new Set(['cluster', 'datastore', 'kube']);

/**
 * Whether a command is a cluster or datastore lifecycle operation: an agent-withheld verb of the
 * cluster, datastore or kube family. Reads in those families (`cluster status`) are not.
 */
export function isClusterLifecycleCommand(command: DecisionCommand): boolean {
  const head = command.pathKey.trim().split(/\s+/)[0] ?? '';
  return command.agentBlocked === true && CLUSTER_FAMILIES.has(head);
}

/** The effective policy of an org with no policy document: the missing-policy default rules. */
const noPolicy: EffectivePolicy = { locked: [], ignoredLocked: [] };

function overrideCovers(list: DecisionOverrides['grandRepos'], name: string | undefined): boolean {
  if (list === '*') return true;
  if (list === null || name === undefined) return false;
  return list.includes(name);
}

const deny = (code: DecisionCode, reason: string, next?: DecisionNext): Decision => ({
  verdict: 'deny',
  code,
  reason,
  ...(next ? { next } : {}),
});

function forkHint(repoName: string | undefined): DecisionNext {
  return { run: `rdc repo fork ${repoName ?? POLICY_DEFAULTS.REPO_NAME_PLACEHOLDER} --tag <tag>` };
}

/** Whether rule 5 (the grand-repo rule) applies to this command and target. */
function targetsGrand(ctx: DecisionContext): boolean {
  if (!ctx.command.grandGuard || ctx.target.isOpsVm) return false;
  if (MUTATES_GRAND_BY_DEFINITION.has(ctx.command.pathKey)) return true;
  return ctx.target.repo?.state !== 'fork';
}

function clusterRule(ctx: DecisionContext, policyCtx: PolicyContext): Decision | null {
  const ceiling = evaluateEffectivePolicy(ctx.policy ?? noPolicy, {
    ...policyCtx,
    isClusterOp: true,
  });
  if (!ceiling.allowed) return deny('CLUSTER_OPS_DENIED', ceiling.reason);
  if (
    ctx.principal.kind === 'agent' &&
    !overrideCovers(ctx.overrides.clusterOps, ctx.target.subject)
  ) {
    return deny(
      'AGENT_OPT_IN_MISSING',
      `"rdc ${ctx.command.pathKey}" is a cluster operation, and no cluster opt-in set by a human covers "${ctx.target.subject ?? POLICY_DEFAULTS.ANY_SUBJECT}".`
    );
  }
  return null;
}

function grandRule(ctx: DecisionContext, policyCtx: PolicyContext): Decision | null {
  const repoName = ctx.target.repo?.name;
  const label = repoName ?? POLICY_DEFAULTS.UNNAMED_REPO;
  const ceiling = evaluateEffectivePolicy(ctx.policy ?? noPolicy, {
    ...policyCtx,
    isGrandRepo: true,
  });
  if (!ceiling.allowed) {
    return deny(
      'GRAND_REPO_DENIED',
      `"rdc ${ctx.command.pathKey}" would change ${label}, a grand repo (not a fork). ${ceiling.reason}`,
      forkHint(repoName)
    );
  }
  if (ctx.principal.kind !== 'agent') return null;
  if (!overrideCovers(ctx.overrides.grandRepos, repoName)) {
    return deny(
      'AGENT_OPT_IN_MISSING',
      `"rdc ${ctx.command.pathKey}" would change ${label}, a grand repo (not a fork), and no grand-repo opt-in set by a human covers it.`,
      forkHint(repoName)
    );
  }
  if (ctx.command.destructive && !ctx.confirmation.granted) {
    return {
      verdict: 'needs_confirmation',
      code: 'CONFIRMATION_REQUIRED',
      reason: `"rdc ${ctx.command.pathKey}" is destructive and would change ${label}, a grand repo. Confirm to proceed.`,
      next: { confirm: { argument: 'confirm', value: repoName ?? ctx.command.pathKey } },
    };
  }
  return null;
}

/** The policy context of the command itself, with the grand and cluster switches left to rules 4-5. */
function policyContextOf({ principal, command, target }: DecisionContext): PolicyContext {
  return {
    userEmail: principal.userEmail,
    orgRole: principal.orgRole,
    commandPath: command.pathKey,
    destructive: command.destructive ?? false,
    isGrandRepo: false,
    isClusterOp: false,
    ...(principal.teamSlug ? { teamSlug: principal.teamSlug } : {}),
    ...(target.machine ? { machineName: target.machine } : {}),
    ...(target.repo ? { repoName: target.repo.name } : {}),
    ...(command.mutationScope ? { mutationScope: command.mutationScope } : {}),
  };
}

/** Rules 2-3: the agent-only command refusals that no policy or opt-in lifts. */
function agentCommandRule({ principal, command, target }: DecisionContext): Decision | null {
  if (principal.kind !== 'agent') return null;
  if (command.agentBlocked && !isClusterLifecycleCommand(command)) {
    return deny('AGENT_BLOCKED', `"rdc ${command.pathKey}" is not available to agents.`);
  }
  if (command.forkBlocked && target.repo?.state === 'fork') {
    return deny(
      'FORK_BLOCKED',
      `"rdc ${command.pathKey}" does not apply to a fork; "${target.repo.name}" is a fork.`
    );
  }
  return null;
}

/** Decide whether `ctx` may run. Pure: the same context always yields the same decision. */
export function decide(ctx: DecisionContext): Decision {
  const policyCtx = policyContextOf(ctx);
  const base = evaluateEffectivePolicy(ctx.policy ?? noPolicy, policyCtx);
  if (!base.allowed) return deny('POLICY_DENIED', base.reason);

  const refusal =
    agentCommandRule(ctx) ??
    (isClusterLifecycleCommand(ctx.command) ? clusterRule(ctx, policyCtx) : null) ??
    (targetsGrand(ctx) ? grandRule(ctx, policyCtx) : null);
  if (refusal) return refusal;

  return { verdict: 'allow', code: 'ALLOWED', reason: base.reason };
}
