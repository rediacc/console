/**
 * The enforcement step every path that runs an `rdc` command calls once
 * (agent/plans/PLAN-rmcp-decide.md Design 2-3): resolve the target, ask `decide`, and refuse
 * anything but `allow`.
 *
 * The caller supplies what only it knows: the principal (a local human or agent, a console or
 * `--proxy` session, a remote-MCP grant), the effective policy it loaded, and the opt-ins of its
 * kind (`readEnvOverrides` locally, the grant row remotely). This module adds the one repo
 * resolver (target.ts) and the one decision function, so no path carries a guard of its own.
 */

import {
  type Decision,
  type DecisionCommand,
  type DecisionOverrides,
  type DecisionPrincipal,
  decide,
  type EffectivePolicy,
} from '@rediacc/shared/policy';
import { resolveTarget, type TargetRef } from './target.js';

/** A `deny` or `needs_confirmation` answer, carried whole so each surface renders it by `code`. */
export class DecisionError extends Error {
  readonly decision: Decision;
  constructor(decision: Decision) {
    super(decision.reason);
    this.name = 'DecisionError';
    this.decision = decision;
  }
}

export interface EnforceArgs {
  principal: DecisionPrincipal;
  command: DecisionCommand;
  target: TargetRef;
  /** The effective policy (org ceiling and team narrowing), or `null` when the org has none. */
  policy: EffectivePolicy | null;
  overrides: DecisionOverrides;
  /** Set on the retry after a `needs_confirmation` answer was confirmed. */
  confirmation?: { granted: boolean };
}

/** Decide `args` and return the `allow` decision; throws `DecisionError` for any other verdict. */
export async function enforce(args: EnforceArgs): Promise<Decision> {
  const decision = decide({
    principal: args.principal,
    command: args.command,
    target: await resolveTarget(args.target),
    policy: args.policy,
    overrides: args.overrides,
    confirmation: args.confirmation ?? { granted: false },
  });
  if (decision.verdict !== 'allow') throw new DecisionError(decision);
  return decision;
}
