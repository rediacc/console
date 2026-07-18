/**
 * Permission policy document.
 *
 * Describes what a user may do through the proxy (`rdc serve`): which commands,
 * against which machines and repos, with which mutation scopes. The document is
 * authored per organization and evaluated by `evaluatePolicy` (evaluate.ts),
 * which both the executor and the permissions UI call so a decision shown in the
 * console is the decision the executor actually makes.
 *
 * ## Command path format (canonical)
 *
 * A command path is the CLI invocation with its arguments stripped, segments
 * separated by SINGLE SPACES, exactly as the user types it:
 *
 *     "repo fork"      "machine status"      "cluster destroy"
 *
 * Not dotted ("repo.fork") and not hyphenated. One format, everywhere: the
 * executor derives it from the command it is about to run, and the policy author
 * writes the same string.
 *
 * ## Glob semantics
 *
 * Patterns match the WHOLE command path. `*` matches any run of characters,
 * spaces included, so it spans segments:
 *
 *     "*"           matches every command
 *     "repo *"      matches "repo fork" and "repo secret set"
 *     "repo"        matches only "repo" itself
 *     "* list"      matches "repo list" and "machine list"
 *
 * The same matcher applies to `machines` and `repos` entries, so "prod-*"
 * scopes a rule to every machine whose name starts with "prod-".
 */

import { z } from 'zod';

/** Mutation classes a rule can permit. Mirrors the CLI's mutation-gate scopes. */
export const MUTATION_SCOPES = ['config', 'infra', 'backup'] as const;
export type MutationScope = (typeof MUTATION_SCOPES)[number];

/** Org roles a policy decision can be made against. */
export const ORG_ROLES = ['owner', 'admin', 'member'] as const;
export type PolicyOrgRole = (typeof ORG_ROLES)[number];

/**
 * One tier of permissions. Every field is optional: an omitted field means
 * "this tier says nothing about that dimension", which lets a user rule refine
 * a single dimension without restating the team's whole rule.
 */
export const PolicyRuleSchema = z.object({
  /**
   * Command allow/deny globs. Omitted entirely means commands are unrestricted
   * at this tier. When present, `allow` is a whitelist: a command must match at
   * least one entry. `deny` always outranks any allow, at any tier.
   */
  commands: z
    .object({
      allow: z.array(z.string().min(1)),
      deny: z.array(z.string().min(1)).optional(),
    })
    .optional(),
  /** Machine-name globs this rule is confined to. Omitted means every machine. */
  machines: z.array(z.string().min(1)).optional(),
  /** Repo-name globs this rule is confined to. Omitted means every repo. */
  repos: z.array(z.string().min(1)).optional(),
  /** Permit operations targeting a grand (root) repo. Omitted means no. */
  allowGrandRepos: z.boolean().optional(),
  /** Permit cluster lifecycle operations. Omitted means no. */
  allowClusterOps: z.boolean().optional(),
  /** Mutation classes permitted. Omitted means mutations are unrestricted. */
  mutationScopes: z.array(z.enum(MUTATION_SCOPES)).optional(),
});
export type PolicyRule = z.infer<typeof PolicyRuleSchema>;

/**
 * The whole policy for one organization.
 *
 * `defaults` is required so a document always has a floor to fall back to.
 * `teams` is keyed by team slug and `users` by user email; the more specific
 * tier wins per dimension (see evaluate.ts for precedence).
 */
export const PolicyDocumentSchema = z.object({
  version: z.literal(1),
  defaults: PolicyRuleSchema,
  teams: z.record(z.string().min(1), PolicyRuleSchema).optional(),
  users: z.record(z.string().min(1), PolicyRuleSchema).optional(),
});
export type PolicyDocument = z.infer<typeof PolicyDocumentSchema>;
