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

import { getCommand } from '@rediacc/shared/cli-contract';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import {
  evaluatePolicy,
  MISSING_POLICY_DEFAULT,
  type PolicyDecision,
  type PolicyDocument,
  PolicyDocumentSchema,
} from '@rediacc/shared/policy';
import type { SessionPrincipal } from './sessions.js';

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
 */
function readPolicyDocument(config: RdcConfig): PolicyDocument | undefined {
  const raw = config.policy;
  if (raw === undefined) return undefined;

  // Re-validate even though the config schema already types this field. The
  // config may have arrived from a remote store, and a document that the schema
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
  return parsed.data;
}

export interface AuthorizeArgs {
  principal: SessionPrincipal;
  /** Space-separated contract path, e.g. "repo fork". */
  commandPath: string;
  config: RdcConfig;
  machineName?: string;
  repoName?: string;
  /** Whether the target repo is a grand (root) repo, when known. */
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

  if (!document) {
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

  const decision = evaluatePolicy(document, {
    userEmail: args.principal.userEmail,
    teamSlug: args.teamSlug,
    orgRole: args.principal.orgRole,
    commandPath: args.commandPath,
    machineName: args.machineName,
    repoName: args.repoName,
    destructive: entry?.destructive ?? false,
    isGrandRepo: args.isGrandRepo,
  });

  if (!decision.allowed) throw new PolicyDenied(decision);
  return decision;
}
