/**
 * The audit record of one AI approval answer (AI3 of agent/plans/PLAN-console-ai-assistant.md).
 *
 * An approval is the moment a person lets an agent run a held command, so the executor records it
 * the way it records a command: synchronously, attributed to the principal the account resolved,
 * and joined to the console run by the request id the tool call runs under. The event is a
 * `cli.command` under the path `ai approval`; `success` is the decision (true for approve, false
 * for reject) and `destructive` the executor's own judgment of the approved command. Params are not
 * shipped, as for every command.
 *
 * An approval that cannot be recorded is withdrawn: the route revokes the grant the ledger left
 * and answers the audit failure, so no approved run happens without its record.
 *
 * The other AI decisions are recorded the same way, each under its own path: the Auto-mode judge's
 * verdict (`ai judge`, success is an allow), a refusal of an approval (`ai refusal`, success false)
 * and each mode change (`ai mode <mode>`). The mode a person chose and the one the judge fell back
 * to are told apart by the neighbouring `ai judge` record that shares the tool call's request id.
 * Only paths and flags are shipped, never a command's parameters, so no secret reaches the record.
 */

import type { ExecutorAuditEvent } from '../serve/deps.js';
import type { SessionPrincipal } from '../serve/sessions.js';

/** The command path an approval answer is recorded under. */
const AI_APPROVAL_AUDIT_PATH = 'ai approval';
/** The command path of an Auto-mode judge verdict. */
const AI_JUDGE_AUDIT_PATH = 'ai judge';
/** The command path of a refused approval. */
const AI_REFUSAL_AUDIT_PATH = 'ai refusal';
/** The command path of a mode change is this prefix and the new mode. */
const AI_MODE_AUDIT_PREFIX = 'ai mode';

type AuditSink = ((event: ExecutorAuditEvent) => Promise<void>) | undefined;

export interface ApprovalAuditInput {
  principal: SessionPrincipal;
  decision: 'approve' | 'reject';
  destructive: boolean;
  /** The request id the held tool call runs under (`<conversation>:<tool call>`). */
  requestId: string;
}

/** The executor audit event of one approval answer. */
function approvalAuditEvent(input: ApprovalAuditInput): ExecutorAuditEvent {
  return {
    principal: input.principal,
    commandPath: AI_APPROVAL_AUDIT_PATH,
    params: {},
    success: input.decision === 'approve',
    exitCode: 0,
    durationMs: 0,
    destructive: input.destructive,
    requestId: input.requestId,
  };
}

/** Ship the record; throws the sink's AuditUnavailableError when it cannot be delivered. */
export async function auditApproval(audit: AuditSink, input: ApprovalAuditInput): Promise<void> {
  await audit?.(approvalAuditEvent(input));
}

export interface AiDecisionAuditInput {
  principal: SessionPrincipal;
  destructive: boolean;
  requestId?: string;
}

function decisionEvent(
  path: string,
  success: boolean,
  input: AiDecisionAuditInput
): ExecutorAuditEvent {
  return {
    principal: input.principal,
    commandPath: path,
    params: {},
    success,
    exitCode: success ? 0 : 1,
    durationMs: 0,
    destructive: input.destructive,
    ...(input.requestId ? { requestId: input.requestId } : {}),
  };
}

/** Record one Auto-mode judge verdict: success for an allow, a failure for a block. */
export async function auditJudgeVerdict(
  audit: AuditSink,
  input: AiDecisionAuditInput & { verdict: 'allow' | 'block' }
): Promise<void> {
  await audit?.(decisionEvent(AI_JUDGE_AUDIT_PATH, input.verdict === 'allow', input));
}

/** Record a refusal of an approval (a missing step-up, a disabled mode). */
export async function auditRefusal(audit: AuditSink, input: AiDecisionAuditInput): Promise<void> {
  await audit?.(decisionEvent(AI_REFUSAL_AUDIT_PATH, false, input));
}

/** Record one mode change under the path `ai mode <mode>`. */
export async function auditModeChange(
  audit: AuditSink,
  input: AiDecisionAuditInput & { mode: string }
): Promise<void> {
  await audit?.(decisionEvent(`${AI_MODE_AUDIT_PREFIX} ${input.mode}`, true, input));
}
