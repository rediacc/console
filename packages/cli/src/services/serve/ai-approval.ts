/**
 * The approval and mode judgements of ai-routes.ts: the modes the policy disables for a caller, and what the executor makes of an approval (destructive, grand repo, step-up). Moved out so the route module stays under the line budget.
 */

import { isPreviewRun, isStepUpMethod } from '@rediacc/shared/auth';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import {
  type AiDisableableMode,
  disabledAiModes,
  type EffectivePolicy,
  mergePolicies,
  PolicyDocumentSchema,
} from '@rediacc/shared/policy';
import { auditApproval, auditRefusal } from '../ai/approval-audit.js';
import { isGrandTarget } from '../ai/autonomy.js';
import { boundEffectivePolicy } from '../config/policy-record.js';
import { toolRequestId } from './ai-chat-tools.js';
import type { ApprovalRequest } from './ai-routes.js';
import { prepareCommand } from './command-dispatch.js';
import type { ExecutorAuditEvent } from './deps.js';
import { clusterSubjectOf, resolveExecutorTarget } from './policy.js';
import type { SessionPrincipal } from './sessions.js';

/** Refusal code of an approval of a destructive or grand-repo command that names no step-up method. */
export const AI_APPROVAL_STEPUP_REQUIRED = 'AI_APPROVAL_STEPUP_REQUIRED';

/** A request these routes refuse before any policy work. */
export class BadAiRequest extends Error {}

/**
 * The effective policy the config carries: the policy records bound to a remote config, else the
 * `policy` field of a local-file config (the same sources serve/policy.ts authorizes against). A
 * malformed local document disables nothing here; authorize() refuses every command under it.
 */
function effectivePolicyOf(config: RdcConfig): EffectivePolicy | null {
  const bound = boundEffectivePolicy(config);
  if (bound) return bound;
  if (config.remote !== undefined || config.policy === undefined) return null;
  const parsed = PolicyDocumentSchema.safeParse(config.policy);
  return parsed.success ? mergePolicies(parsed.data) : null;
}

/** The modes the policy disables for this caller (D6), in `AI_DISABLEABLE_MODES` order. */
export function disabledModesFor(
  config: RdcConfig,
  principal: SessionPrincipal
): AiDisableableMode[] {
  const effective = effectivePolicyOf(config);
  if (!effective) return [];
  return disabledAiModes(effective, {
    userEmail: principal.userEmail,
    ...(principal.teamSlug ? { teamSlug: principal.teamSlug } : {}),
  });
}

function stringOf(name: string | null, bag: Record<string, unknown>): string | undefined {
  const value = name ? bag[name] : undefined;
  return typeof value === 'string' ? value : undefined;
}

/**
 * What the executor itself makes of an approval: whether the command is destructive (and not a
 * preview) and whether its target is a grand repo, and the refusal of an approval of either that
 * names no step-up method.
 */
export async function judgeApproval(
  body: ApprovalRequest,
  config: RdcConfig | undefined
): Promise<{ grand: boolean; destructive: boolean } | { refusal: Record<string, unknown> }> {
  const { pathKey, params, positionals } = body.command;
  const { entry } = prepareCommand(pathKey, params, positionals);
  const target = await resolveExecutorTarget(
    entry,
    {
      ref: stringOf(entry.repoOption, params) ?? stringOf(entry.repoPositional, positionals),
      machine:
        stringOf(entry.machineOption, params) ?? stringOf(entry.machinePositional, positionals),
      subject: clusterSubjectOf(entry, positionals),
    },
    config
  );
  const grand = isGrandTarget(target);
  const destructive = entry.severity === 'destructive' && !isPreviewRun(entry, params);
  const needsStepUp = body.decision === 'approve' && (grand || destructive);
  if (!needsStepUp || isStepUpMethod(body.stepUpMethod)) return { grand, destructive };
  const why = grand ? `targets the grand repo "${target.repo?.name}"` : 'is destructive';
  return {
    refusal: {
      error: `Approving "rdc ${pathKey}" needs a fresh re-authentication: the command ${why}.`,
      code: AI_APPROVAL_STEPUP_REQUIRED,
      grand,
      destructive,
    },
  };
}

type AuditSink = ((event: ExecutorAuditEvent) => Promise<void>) | undefined;

/** Audit one redeemed answer; an approval whose record cannot be delivered loses its grant. */
export async function recordApproval(
  audit: AuditSink,
  ledger: {
    revokeGrant(
      principal: SessionPrincipal,
      conversationId: string,
      command: ApprovalRequest['command']
    ): void;
  },
  principal: SessionPrincipal,
  body: ApprovalRequest,
  judged: { destructive: boolean }
): Promise<void> {
  try {
    await auditApproval(audit, {
      principal,
      decision: body.decision,
      pathKey: body.command.pathKey,
      destructive: judged.destructive,
      requestId: toolRequestId(body.conversationId, body.toolCallId),
    });
  } catch (error) {
    ledger.revokeGrant(principal, body.conversationId, body.command);
    throw error;
  }
}

/** Audit the refusal of an approval the executor judged needs a step-up. */
export function recordRefusal(
  audit: AuditSink,
  principal: SessionPrincipal,
  body: ApprovalRequest,
  refusal: { destructive?: unknown }
): Promise<void> {
  return auditRefusal(audit, {
    principal,
    pathKey: body.command.pathKey,
    destructive: Boolean(refusal.destructive),
    requestId: toolRequestId(body.conversationId, body.toolCallId),
  });
}
