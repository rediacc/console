/**
 * The executor's autonomy gate (AI3 of agent/plans/PLAN-console-ai-assistant.md, D2, D4 and D6).
 *
 * `decide()` answers first, for an agent principal, and its refusal or confirmation always wins.
 * When it allows, the conversation's mode decides whether the command still waits for the user:
 *
 *   - a read (severity `none`) runs in every mode;
 *   - a grand-repo target and a destructive command wait in every mode, Skip included;
 *   - a `caution` command waits in Ask, runs in Skip, and in Auto runs only on the judge's allow
 *     (judge.ts), a judge failure being a block;
 *   - an exact chat allow rule (one the user asked to remember when approving) lets a `caution`
 *     command run in any mode, matched on the whole argv hash and never on a pattern.
 *
 * A mode the org or team policy disabled (`aiModesDisabled`) reads as Ask, so a conversation
 * stored in Auto or Skip before the policy changed never runs under the disabled mode.
 */

import type { AiApprovalCommand, AiApprovalRisk } from '@rediacc/shared/cli-contract/wire';
import type { AiDisableableMode, DecisionTarget } from '@rediacc/shared/policy';
import type { AiMode } from '../serve/ai-routes.js';
import type { SessionPrincipal } from '../serve/sessions.js';
import { argvHashOf } from './approvals.js';

/** The mode a conversation starts in (D4): every action asks. */
export const DEFAULT_AI_MODE: AiMode = 'ask';

/** Codes of the holds the gate places on a command `decide()` allowed. */
export const AI_HOLD_GRAND = 'AI_HOLD_GRAND';
export const AI_HOLD_DESTRUCTIVE = 'AI_HOLD_DESTRUCTIVE';
export const AI_HOLD_ASK = 'AI_HOLD_ASK';
export const AI_HOLD_JUDGE = 'AI_HOLD_JUDGE';

/** Exact allow rules kept per conversation; a rule beyond this is not remembered. */
const MAX_ALLOW_RULES = 50;

const keyOf = (principal: SessionPrincipal, conversationId: string): string =>
  `${principal.orgId}\u0000${principal.userId}\u0000${conversationId}`;

/** The mode the gate enforces: the stored one, or Ask when the policy disabled it. */
export function effectiveMode(mode: AiMode, disabled: readonly AiDisableableMode[]): AiMode {
  return (disabled as readonly string[]).includes(mode) ? 'ask' : mode;
}

/** A grand-repo target as the grand-repo rule reads it: unresolved counts as grand; ops VMs never do. */
export function isGrandTarget(target: DecisionTarget): boolean {
  return !!target.repo && target.repo.state !== 'fork' && !target.isOpsVm;
}

/**
 * The risk of a command as the approval surfaces show it. `destructive` is the contract's own
 * severity with a preview run excluded by the caller; a changing command on a grand target is
 * `grand` whatever its severity.
 */
export function riskOf(args: {
  severity: 'none' | 'caution' | 'destructive';
  preview: boolean;
  target: DecisionTarget;
}): AiApprovalRisk {
  if (args.severity === 'none' || args.preview) return 'safe';
  if (isGrandTarget(args.target)) return 'grand';
  return args.severity === 'destructive' ? 'destructive' : 'caution';
}

/** Each conversation's mode and exact allow rules, per verified principal; RAM only. */
export class AiConversationStore {
  private readonly modes = new Map<string, AiMode>();
  private readonly rules = new Map<string, Set<string>>();

  set(principal: SessionPrincipal, conversationId: string, mode: AiMode): void {
    this.modes.set(keyOf(principal, conversationId), mode);
  }

  get(principal: SessionPrincipal, conversationId: string): AiMode {
    return this.modes.get(keyOf(principal, conversationId)) ?? DEFAULT_AI_MODE;
  }

  /** Remember an exact allow rule: this argv, in this conversation, for this principal. */
  allowExact(
    principal: SessionPrincipal,
    conversationId: string,
    command: AiApprovalCommand
  ): void {
    const key = keyOf(principal, conversationId);
    const set = this.rules.get(key) ?? new Set<string>();
    const hash = argvHashOf(command);
    if (set.has(hash)) return;
    // At the cap the oldest rule makes room, so the approval the user just asked to remember is the one kept.
    if (set.size >= MAX_ALLOW_RULES) {
      const oldest = set.values().next().value;
      if (oldest !== undefined) set.delete(oldest);
    }
    set.add(hash);
    this.rules.set(key, set);
  }

  allowsExact(
    principal: SessionPrincipal,
    conversationId: string,
    command: AiApprovalCommand
  ): boolean {
    return this.rules.get(keyOf(principal, conversationId))?.has(argvHashOf(command)) ?? false;
  }
}

export interface AiHold {
  code: string;
  reason: string;
}

/**
 * Whether a command `decide()` allowed still waits for the user. `judge` is asked only in Auto
 * mode for a `caution` command; it answers true for an allow.
 */
export async function autonomyHold(args: {
  mode: AiMode;
  risk: AiApprovalRisk;
  pathKey: string;
  exactlyAllowed: boolean;
  judge?: () => Promise<boolean>;
}): Promise<AiHold | null> {
  const { mode, risk, pathKey } = args;
  if (risk === 'safe') return null;
  if (risk === 'grand') {
    return {
      code: AI_HOLD_GRAND,
      reason: `"rdc ${pathKey}" targets a grand repo, which always takes an approval.`,
    };
  }
  if (risk === 'destructive') {
    return {
      code: AI_HOLD_DESTRUCTIVE,
      reason: `"rdc ${pathKey}" is destructive, which always takes an approval.`,
    };
  }
  if (args.exactlyAllowed || mode === 'skip') return null;
  if (mode === 'auto' && args.judge && (await args.judge())) return null;
  return mode === 'auto'
    ? { code: AI_HOLD_JUDGE, reason: `The Auto-mode judge did not allow "rdc ${pathKey}".` }
    : { code: AI_HOLD_ASK, reason: `The conversation is in Ask mode: "rdc ${pathKey}" waits.` };
}
