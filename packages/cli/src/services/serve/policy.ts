/**
 * Authorization at the executor.
 *
 * This is where the local guardrail environment variables
 * (REDIACC_ALLOW_GRAND_REPO and friends) are replaced by something an
 * enterprise can actually rely on. Those variables were trust-rooted in the
 * caller's own /proc ancestry, which is fine for a laptop and meaningless
 * across a network: the client asserting "I am allowed" is not evidence.
 *
 * Here, authorization is data. The rules live inside the ENCRYPTED config, so
 * Rediacc cannot read them, and they are evaluated against a principal the
 * ACCOUNT SERVER resolved, not one the client claimed. The client-side prompts
 * remain, but they are UX; this is the enforcement.
 */

import { CLI_CONTRACT, type ContractCommand, getCommand } from '@rediacc/shared/cli-contract';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import {
  evaluatePolicy,
  findStaleCommandGlobs,
  MISSING_POLICY_DEFAULT,
  type PolicyDecision,
  type PolicyDocument,
  PolicyDocumentSchema,
  staleDenyRefusal,
} from '@rediacc/shared/policy';
import { parseRef } from '@rediacc/shared/ref';
import { configService } from '../config/config-resources.js';
import {
  createOutputState,
  createRequestConfigScope,
  runInRequestContext,
} from '../core/request-context.js';
import type { SessionPrincipal } from './sessions.js';

/** Every command this binary actually has, for checking policy globs against. */
const LIVE_COMMANDS: readonly string[] = CLI_CONTRACT.commands.map((c) => c.pathKey);

/** Raised when policy refuses a command. Carries the reason for CLI and audit. */
export class PolicyDenied extends Error {
  constructor(readonly decision: PolicyDecision) {
    super(decision.reason);
    this.name = 'PolicyDenied';
  }
}

/**
 * The policy document stored in the config, if any.
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

  const stale = findStaleCommandGlobs(parsed.data, LIVE_COMMANDS);
  if (stale.deny.length > 0) throw new Error(staleDenyRefusal(stale.deny));

  return parsed.data;
}

export interface AuthorizeArgs {
  principal: SessionPrincipal;
  /** Space-separated contract path, e.g. "repo fork". */
  commandPath: string;
  config: RdcConfig;
  machineName?: string;
  repoName?: string;
  /**
   * Whether this command MUTATES a grand (root) repo. Computed by the executor
   * with resolveGrandRepoMutation(), never taken from the client; undefined for
   * a command the CLI's grand-repo guard does not cover (every read).
   */
  isGrandRepo?: boolean;
  /** Team slug the principal acts under, when the org models one. */
  teamSlug?: string;
}

/**
 * Decide whether this principal may run this command, and throw if not.
 *
 * The destructive flag comes from the CONTRACT, not from the request: a client
 * cannot talk its way out of a destructive-command rule by omitting a field.
 */
export function authorize(args: AuthorizeArgs): PolicyDecision {
  const entry = getCommand(args.commandPath);
  const document = readPolicyDocument(args.config);

  if (!document) return authorizeWithoutDocument(args);

  const context = {
    userEmail: args.principal.userEmail,
    teamSlug: args.teamSlug,
    orgRole: args.principal.orgRole,
    commandPath: args.commandPath,
    machineName: args.machineName,
    repoName: args.repoName,
    destructive: entry?.destructive ?? false,
  };
  const decision = evaluatePolicy(document, context);
  if (!decision.allowed) throw new PolicyDenied(decision);

  // Grand-ness is judged on its own so its refusal can name the way out, which the shared evaluator's reason does not.
  if (args.isGrandRepo && !evaluatePolicy(document, { ...context, isGrandRepo: true }).allowed) {
    throw new PolicyDenied({ allowed: false, reason: grandRepoRefusal(args) });
  }
  return decision;
}

/** The decision when the config carries no policy document at all. */
function authorizeWithoutDocument(args: AuthorizeArgs): PolicyDecision {
  // A grand-repo mutation is refused by default: with no document there is no `allowGrandRepos` to opt in with, whatever the role. This is the executor's copy of the CLI's agent grand-repo guard, which cannot run here (the executor is not an agent, and a proxied command never reaches the local guard).
  if (args.isGrandRepo) {
    throw new PolicyDenied({ allowed: false, reason: grandRepoRefusal(args) });
  }
  const allowed = MISSING_POLICY_DEFAULT[args.principal.orgRole];
  const decision: PolicyDecision = {
    allowed,
    reason: allowed
      ? `No policy document exists yet, and ${args.principal.orgRole}s are allowed by default. Author one in the console under Permissions.`
      : `No policy document exists yet, so only owners and admins may run commands through the executor. Ask an owner to grant your team access under Permissions.`,
  };
  if (!allowed) throw new PolicyDenied(decision);
  return decision;
}

function grandRepoRefusal(args: AuthorizeArgs): string {
  const target = args.repoName
    ? `would change ${args.repoName}, which is a grand repo (not a fork)`
    : 'would change a grand repo (not a fork)';
  return (
    `"rdc ${args.commandPath}" ${target}, and the executor refuses grand-repo changes by default. ` +
    `Fork it first (rdc repo fork <name> --tag <tag>) and target the fork, or allow grand repos in the policy (allowGrandRepos).`
  );
}

/**
 * A command that changes nothing: annotated as a read (timeout class `read`)
 * and not destructive. Anything unannotated counts as a change, so a command
 * nobody classified is held to the stricter rule.
 */
export function isReadOnlyCommand(entry: ContractCommand): boolean {
  return entry.timeout === 'read' && entry.destructive !== true;
}

/**
 * Commands whose effect lands on the GRAND repo whatever their ref names:
 * `repo promote <fork>` swaps the fork into its grand's place.
 */
const MUTATES_GRAND_BY_DEFINITION: ReadonlySet<string> = new Set(['repo promote']);

/**
 * Whether a command would mutate a grand repo, decided at the executor.
 *
 * The COMMAND set is the CLI guard's own: the contract's `grandGuard`, the same
 * COMMAND_METADATA flag `assertCommandPolicy` reads (utils/command-policy.ts).
 * A command without it (every read, and `repo fork`, the safe way off a grand
 * repo) returns undefined and is never refused on grand-ness.
 *
 * The REPO test is the CLI guard's own too: a repo is a fork exactly when its
 * config record has a `grandGuid` naming another repository, looked up through
 * configService.getRepository with the same `name[:tag]` key the action bodies
 * pass. Unlike the local guard, it FAILS CLOSED: a ref that does not parse,
 * does not resolve, or is absent counts as grand, because an executor facing
 * the network must not wave through what it could not identify.
 *
 * `config` is the request-scoped config (the container tier); without it the
 * lookup reads the daemon's enrolled config, as the dispatched command will.
 */
export async function resolveGrandRepoMutation(
  entry: ContractCommand,
  repoRef: string | undefined,
  config?: RdcConfig
): Promise<boolean | undefined> {
  if (!entry.grandGuard) return undefined;
  if (MUTATES_GRAND_BY_DEFINITION.has(entry.pathKey)) return true;
  if (!repoRef) return true;

  let key: string;
  try {
    const parsed = parseRef(repoRef);
    key = parsed.tag ? `${parsed.name}:${parsed.tag}` : parsed.name;
  } catch {
    return true;
  }

  const lookup = () => configService.getRepository(key);
  const repo = config
    ? await runInRequestContext(
        {
          output: createOutputState(),
          stdout: [],
          stderr: [],
          config: createRequestConfigScope(config),
        },
        lookup
      )
    : await lookup();

  const isFork = !!(repo?.grandGuid && repo.grandGuid !== repo.repositoryGuid);
  return !isFork;
}
