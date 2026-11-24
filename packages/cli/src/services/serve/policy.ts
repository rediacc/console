/**
 * Authorization at the executor: its enforcement point for the one decision function, `decide`
 * (packages/shared/src/policy/decide.ts; agent/plans/PLAN-rmcp-decide.md Design 3).
 *
 * The local guardrail environment variables (REDIACC_ALLOW_GRAND_REPO and friends) are
 * trust-rooted in the caller's own /proc ancestry, which is fine for a laptop and meaningless
 * across a network: a client asserting its own permission is not evidence. Here, authorization is
 * data. The rules of a remote config live in their own ENCRYPTED policy record
 * (PLAN-rmcp-policy-record.md), so Rediacc cannot read them and a member who may push the config
 * cannot rewrite them; they are evaluated against a principal the ACCOUNT SERVER resolved, not one
 * the client claimed.
 *
 * The answer comes from the same `decide` the CLI and both MCP servers reach, so a command is
 * refused or allowed the same way on every path (D18). A console or `--proxy` caller is a human
 * principal; a remote-MCP grant is an agent principal whose opt-ins come from its grant row (D23).
 */

import { CLI_CONTRACT, type ContractCommand, getCommand } from '@rediacc/shared/cli-contract';
import { POLICY_DEFAULTS } from '@rediacc/shared/config/defaults';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import {
  type Decision,
  type DecisionCommand,
  type DecisionOverrides,
  type DecisionPrincipal,
  type DecisionTarget,
  decide,
  type EffectivePolicy,
  findStaleCommandGlobs,
  MUTATES_GRAND_BY_DEFINITION,
  mergePolicies,
  type PolicyDecision,
  type PolicyDocument,
  PolicyDocumentSchema,
  staleDenyRefusal,
} from '@rediacc/shared/policy';
import { boundEffectivePolicy } from '../config/policy-record.js';
import {
  createOutputState,
  createRequestConfigScope,
  runInRequestContext,
} from '../core/request-context.js';
import { DecisionError } from '../policy/enforce.js';
import { resolveTarget, type TargetRef } from '../policy/target.js';
import type { SessionPrincipal } from './sessions.js';

/** Every command this binary actually has, for checking policy globs against. */
const LIVE_COMMANDS: readonly string[] = CLI_CONTRACT.commands.map((c) => c.pathKey);

/**
 * Raised when `decide` answers anything but `allow` at the executor. It is the enforcement step's
 * `DecisionError`, so it carries the whole decision (verdict, stable code, next step) for the HTTP
 * answer and the audit.
 */
export class PolicyDenied extends DecisionError {
  constructor(...args: ConstructorParameters<typeof DecisionError>) {
    super(...args);
    this.name = 'PolicyDenied';
  }
}

/** A policy document whose deny rule names a command that does not exist protects nothing, so it is refused. */
function refuseStaleDeny(document: PolicyDocument): void {
  const stale = findStaleCommandGlobs(document, LIVE_COMMANDS);
  if (stale.deny.length > 0) throw new Error(staleDenyRefusal(stale.deny));
}

/**
 * The policy a command is authorized against, or `null` when there is none.
 *
 * A config the container loader opened carries the effective policy it read
 * from the policy records (org ceiling, team narrowing), bound to the document;
 * that is the only source for a remote config, so a `policy` field forged into
 * a pushed config decides nothing. A remote config with no bound policy has no
 * policy. A LOCAL-file config (no `remote` block) keeps its own `policy` field
 * as the ceiling (D24).
 */
function effectivePolicyOf(config: RdcConfig): EffectivePolicy | null {
  const bound = boundEffectivePolicy(config);
  if (bound) {
    if (bound.org) refuseStaleDeny(bound.org);
    if (bound.team) refuseStaleDeny(bound.team);
    return bound.org || bound.team ? bound : null;
  }
  if (config.remote !== undefined) return null;
  const document = readPolicyDocument(config);
  return document ? mergePolicies(document) : null;
}

/**
 * The policy document stored in a local-file config, if any.
 *
 * A malformed document is a hard error rather than a silent fall-through to the
 * default. Someone who wrote rules and got the shape wrong must hear about it;
 * quietly ignoring them would be the worst possible failure, since it would look
 * like the rules were in force.
 *
 * A document with a STALE DENY GLOB is that same failure, one level subtler: it
 * is well-formed, it parses, and its deny rule protects NOTHING because the
 * command it names does not exist. That is how a rename fails open, the command
 * an organization explicitly forbade becomes permitted, silently. It is refused
 * here for the reason stated above, and the reason names the glob so the author
 * can re-key it (a rename is the likeliest cause, and a re-key the likeliest fix).
 */
function readPolicyDocument(config: RdcConfig): PolicyDocument | undefined {
  const raw = config.policy;
  if (raw === undefined) return undefined;

  // Re-validate even though the config schema already types this field. The config may have arrived from a remote store, and a document that the schema
  // let through in a `.loose()` parse must still be a well-formed rule set
  // before anything is authorized against it.
  const parsed = PolicyDocumentSchema.safeParse(raw);
  if (!parsed.success) {
    throw new Error(
      `The policy document in this config is not valid, so no command can be authorized against it. ` +
        `Fix it in the console under Permissions. Details: ${parsed.error.issues
          .map((i) => `${i.path.join('.')}: ${i.message}`)
          .join('; ')}`
    );
  }

  refuseStaleDeny(parsed.data);

  return parsed.data;
}

/**
 * The agent opt-ins one grant row carries (PLAN-rmcp-agent-grants.md Design 2, `overrides_json`):
 * `allowGrandRepos` is `true` for every repo or a list of repo names, `allowClusterOps` a switch.
 */
export interface AgentGrantOverrides {
  allowGrandRepos: boolean | readonly string[];
  allowClusterOps: boolean;
}

function grandReposOf(
  repos: AgentGrantOverrides['allowGrandRepos']
): DecisionOverrides['grandRepos'] {
  if (repos === true) return '*';
  if (repos === false || repos.length === 0) return null;
  return repos;
}

/**
 * A grant row's opt-ins in the overrides shape `decide` takes (`source: 'grant'`). `true` covers
 * every name, `false` or an empty list grants nothing. The policy ceiling still applies on top
 * (D20: an opt-in never exceeds the policy).
 */
export function grantOverrides(grant: AgentGrantOverrides): DecisionOverrides {
  const grandRepos = grandReposOf(grant.allowGrandRepos);
  const clusterOps = grant.allowClusterOps ? '*' : null;
  return {
    grandRepos,
    clusterOps,
    source: grandRepos === null && clusterOps === null ? 'none' : 'grant',
  };
}

/** The opt-ins of a human principal: none, since the opt-in rule binds agents only (D22). */
const NO_OVERRIDES: DecisionOverrides = { grandRepos: null, clusterOps: null, source: 'none' };

export interface AuthorizeArgs {
  /** The principal the account server resolved; its `teamSlug` picks the team tier of the policy. */
  principal: SessionPrincipal;
  /** Space-separated contract path, e.g. "repo fork". */
  commandPath: string;
  config: RdcConfig;
  /**
   * The resolved target (`resolveExecutorTarget`), computed by the executor from the config the
   * command will run against and never taken from the client. Absent for a route that names no
   * repo (`job logs`, `job cancel`): the target is then `machineName` alone, which a grand-guarded
   * command reads as a grand (fail closed).
   */
  target?: DecisionTarget;
  machineName?: string;
  /** Present only for a remote-MCP grant principal: makes the principal an agent with these opt-ins. */
  agentGrant?: AgentGrantOverrides;
  /** Set on the retry after a `needs_confirmation` answer was confirmed. */
  confirmation?: { granted: boolean };
}

function principalOf(args: AuthorizeArgs): DecisionPrincipal {
  const { principal } = args;
  return {
    kind: args.agentGrant ? 'agent' : 'human',
    userEmail: principal.userEmail,
    orgRole: principal.orgRole,
    ...(principal.teamSlug ? { teamSlug: principal.teamSlug } : {}),
  };
}

/** The contract fields `decide` reads. */
function decisionCommandOf(entry: ContractCommand): DecisionCommand {
  return {
    pathKey: entry.pathKey,
    ...(entry.destructive ? { destructive: true } : {}),
    ...(entry.grandGuard ? { grandGuard: true } : {}),
    ...(entry.forkBlocked ? { forkBlocked: true } : {}),
    ...(entry.agentBlocked ? { agentBlocked: true } : {}),
  };
}

/**
 * Decide whether this principal may run this command, and throw `PolicyDenied` for any answer but
 * `allow`.
 *
 * The command's flags (destructive, grand-guarded, fork-blocked, agent-blocked) come from the
 * CONTRACT, not from the request: a client cannot talk its way out of a rule by omitting a field.
 */
export function authorize(args: AuthorizeArgs): PolicyDecision {
  const entry = getCommand(args.commandPath);
  if (!entry) throw new Error(`There is no "rdc ${args.commandPath}" command to authorize.`);
  const machineOnly: DecisionTarget = {
    ...(args.machineName ? { machine: args.machineName } : {}),
    isOpsVm: false,
  };
  const command = decisionCommandOf(entry);
  const target = args.target ?? machineOnly;
  const policy = effectivePolicyOf(args.config);
  const decision = decide({
    principal: principalOf(args),
    command,
    target,
    policy,
    overrides: args.agentGrant ? grantOverrides(args.agentGrant) : NO_OVERRIDES,
    confirmation: args.confirmation ?? { granted: false },
  });
  if (decision.verdict === 'deny') throw new PolicyDenied(decision);
  if (policy === null && mutatesGrand(command, target)) {
    throw new PolicyDenied(noPolicyGrandRefusal(command, target));
  }
  if (decision.verdict !== 'allow') throw new PolicyDenied(decision);
  return { allowed: true, reason: decision.reason };
}

/**
 * Whether a command would change a grand repo: the grand-repo rule's own test in `decide` (a
 * `grandGuard` command whose target is not a fork, an unresolved or absent repo counting as grand,
 * `repo promote` always landing on the grand, an ops-VM placement exempt).
 */
function mutatesGrand(command: DecisionCommand, target: DecisionTarget): boolean {
  if (!command.grandGuard || target.isOpsVm) return false;
  if (MUTATES_GRAND_BY_DEFINITION.has(command.pathKey)) return true;
  return target.repo?.state !== 'fork';
}

/**
 * The executor's one deviation from `decide`: with NO policy document, a grand-repo change is
 * refused whatever the principal's role, where the decision table's row null-human-owner-grand
 * lets an owner or admin through. That row trusts the principal kind, and the executor cannot tell
 * an agent from a human: every console and `--proxy` caller arrives as a human principal, and the
 * client-side agent check (enforceProxiedAgentCommand in cli.ts) does not bind an agent that calls
 * the executor API directly. So the executor fails closed, as it did before `decide` (security
 * review finding b2f0bd2f.1), and the way past is a policy that sets `allowGrandRepos`, which then
 * goes through `decide` like every other case with a document.
 */
function noPolicyGrandRefusal(command: DecisionCommand, target: DecisionTarget): Decision {
  const repoName = target.repo?.name;
  const subject = repoName
    ? `would change ${repoName}, a grand repo (not a fork)`
    : 'would change a grand repo (not a fork)';
  return {
    verdict: 'deny',
    code: 'GRAND_REPO_DENIED',
    reason:
      `"rdc ${command.pathKey}" ${subject}, and the executor refuses grand-repo changes with no policy: ` +
      `grand-repo changes need an org policy with allowGrandRepos. ` +
      `Target a fork instead, or author such a policy in the console under Permissions.`,
    next: { run: `rdc repo fork ${repoName ?? POLICY_DEFAULTS.REPO_NAME_PLACEHOLDER} --tag <tag>` },
  };
}

/**
 * The name a cluster opt-in must cover: the command's cluster or datastore positional as typed.
 * Absent for a cluster verb that names a machine (`cluster join`), which only a `*` opt-in covers.
 */
export function clusterSubjectOf(
  entry: ContractCommand,
  positionals: Record<string, unknown>
): string | undefined {
  const named = entry.positionals.find((p) => p.kind === 'cluster' || p.kind === 'datastore-ref');
  const value = named ? positionals[named.name] : undefined;
  return typeof value === 'string' ? value : undefined;
}

/**
 * Resolve the target of a command at the executor, through the one repo resolver every path uses
 * (services/policy/target.ts): a fork is a repo whose config record names another repo as its
 * grand, a ref that does not parse or resolve comes back `unresolved` (which `decide` treats as a
 * grand), and an ops-VM placement is marked so the grand-repo rule skips it.
 *
 * `config` is the request-scoped config (the container tier); without it the lookups read the
 * daemon's enrolled config, as the dispatched command will.
 *
 * `repo promote <fork>` lands on the grand the fork replaces, so its target names that grand.
 */
export async function resolveExecutorTarget(
  entry: ContractCommand,
  input: TargetRef,
  config: RdcConfig | undefined
): Promise<DecisionTarget> {
  const resolve = () => resolveTarget(input);
  const target = config
    ? await runInRequestContext(
        {
          output: createOutputState(),
          stdout: [],
          stderr: [],
          config: createRequestConfigScope(config),
        },
        resolve
      )
    : await resolve();
  if (!target.repo || !MUTATES_GRAND_BY_DEFINITION.has(entry.pathKey)) return target;
  const [grandName = target.repo.name] = target.repo.name.split(':');
  return { ...target, repo: { name: grandName, state: 'grand' } };
}

/**
 * A command that changes nothing: annotated as a read (timeout class `read`)
 * and not destructive. Anything unannotated counts as a change, so a command
 * nobody classified is held to the stricter rule.
 */
export function isReadOnlyCommand(entry: ContractCommand): boolean {
  return entry.timeout === 'read' && entry.destructive !== true;
}
