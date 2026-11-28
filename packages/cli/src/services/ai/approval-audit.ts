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
import type { AiGateCall } from './tools.js';

/** The command path an approval answer is recorded under. */
const AI_APPROVAL_AUDIT_PATH = 'ai approval';
/** The command path of an Auto-mode judge verdict. */
const AI_JUDGE_AUDIT_PATH = 'ai judge';
/** The command path of a refused approval. */
const AI_REFUSAL_AUDIT_PATH = 'ai refusal';
/** The command path of a mode change is this prefix and the new mode. */
const AI_MODE_AUDIT_PREFIX = 'ai mode';

/** The most characters of a command path the account's audit schema accepts. */
const COMMAND_PATH_MAX = 200;

/**
 * A command path key: lowercase words (letters and single hyphens) joined by single spaces. That is
 * the shape of a command path and no more: a digit, flag, `=` or quote is refused, but a shape
 * cannot tell a command word from a purely alphabetic value, so the caller passes the key of a
 * command it holds.
 */
const COMMAND_PATH_KEY = /^[a-z]+(-[a-z]+)*( [a-z]+(-[a-z]+)*)*$/;

/**
 * The path of a decision about one command: `<path> <pathKey>` when the command is known, so the
 * account side turns the record into `console.ai.approval` with the command it decided. The pathKey
 * is a command path, never a parameter: a key that is not shaped like one (the approval route takes
 * it from the client) or that would not fit the schema whole is left out, so the record names the
 * decision only, never a truncated or parameter-bearing command.
 */
function decisionPath(path: string, pathKey: string | undefined): string {
  if (!pathKey || !COMMAND_PATH_KEY.test(pathKey)) return path;
  const full = `${path} ${pathKey}`;
  return full.length > COMMAND_PATH_MAX ? path : full;
}

type AuditSink = ((event: ExecutorAuditEvent) => Promise<void>) | undefined;

export interface ApprovalAuditInput {
  principal: SessionPrincipal;
  decision: 'approve' | 'reject';
  /** The approved command's path key. */
  pathKey?: string;
  destructive: boolean;
  /** The request id the held tool call runs under (`<conversation>:<tool call>`). */
  requestId: string;
}

/** The executor audit event of one approval answer. */
function approvalAuditEvent(input: ApprovalAuditInput): ExecutorAuditEvent {
  return {
    principal: input.principal,
    commandPath: decisionPath(AI_APPROVAL_AUDIT_PATH, input.pathKey),
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
  /** The command the decision is about: a judge verdict and a refusal name it. */
  pathKey?: string;
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
    commandPath: decisionPath(path, input.pathKey),
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

/** Record a refusal: an approval without its step-up, or a request for a mode that is disabled. */
export async function auditRefusal(audit: AuditSink, input: AiDecisionAuditInput): Promise<void> {
  await audit?.(decisionEvent(AI_REFUSAL_AUDIT_PATH, false, input));
}

/** Record one mode change under the path `ai mode <mode>`. */
export async function auditModeChange(
  audit: AuditSink,
  input: AiDecisionAuditInput & { mode: string }
): Promise<void> {
  await audit?.(
    decisionEvent(`${AI_MODE_AUDIT_PREFIX} ${input.mode}`, true, { ...input, pathKey: undefined })
  );
}

/**
 * Record a judge verdict and, when the judge fell back to Ask, that mode change. The tool call's
 * request id joins both records to the run and tells the account the mode change was the judge's.
 */
export async function auditJudgment(
  audit: AuditSink,
  input: Pick<AiDecisionAuditInput, 'principal' | 'requestId'> & {
    call: Pick<AiGateCall, 'entry' | 'command'>;
    judgment: { verdict: { verdict: 'allow' | 'block' }; fallback?: unknown };
  }
): Promise<void> {
  const { call, judgment, ...base } = input;
  const record = { ...base, destructive: call.entry.severity === 'destructive' };
  await auditJudgeVerdict(audit, {
    ...record,
    pathKey: call.command.pathKey,
    verdict: judgment.verdict.verdict,
  });
  if (judgment.fallback) await auditModeChange(audit, { ...record, mode: 'ask' });
}
