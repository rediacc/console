/**
 * Stable codes for the answers of `decide` (decide.ts).
 *
 * Every surface that runs an `rdc` command (the CLI, the local MCP server, the remote MCP Worker,
 * `rdc --proxy` and the web console) reports a decision by one of these codes, so a script or an
 * agent can branch on the code instead of parsing a message. The codes are part of the JSON output
 * contract: renaming one is a breaking change for every consumer.
 */

export const DECISION_CODES = [
  /** The command may run. */
  'ALLOWED',
  /** The policy (org ceiling, team narrowing, or the missing-policy default) refuses the command. */
  'POLICY_DENIED',
  /** The policy refuses a change to a grand (root) repo; `allowGrandRepos` does not admit it. */
  'GRAND_REPO_DENIED',
  /** The policy refuses a cluster or datastore lifecycle operation; `allowClusterOps` is not set. */
  'CLUSTER_OPS_DENIED',
  /** An agent acts where the policy permits it, but no human-set session opt-in covers the target. */
  'AGENT_OPT_IN_MISSING',
  /** The command does not apply to a fork (an interim environment), and an agent named a fork. */
  'FORK_BLOCKED',
  /** The command is never available to an agent, whatever the policy or opt-in says. */
  'AGENT_BLOCKED',
  /** The command may run once the caller confirms it (MCP elicitation, else a confirm argument). */
  'CONFIRMATION_REQUIRED',
] as const;

export type DecisionCode = (typeof DECISION_CODES)[number];

/** The three verdicts a decision can carry. */
export const DECISION_VERDICTS = ['allow', 'deny', 'needs_confirmation'] as const;

export type DecisionVerdict = (typeof DECISION_VERDICTS)[number];
