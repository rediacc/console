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
 */

import type { ExecutorAuditEvent } from '../serve/deps.js';
import type { SessionPrincipal } from '../serve/sessions.js';

/** The command path an approval answer is recorded under. */
const AI_APPROVAL_AUDIT_PATH = 'ai approval';

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
export async function auditApproval(
  audit: ((event: ExecutorAuditEvent) => Promise<void>) | undefined,
  input: ApprovalAuditInput
): Promise<void> {
  await audit?.(approvalAuditEvent(input));
}
