/**
 * Single-use AI approval tokens (AI3 of agent/plans/PLAN-console-ai-assistant.md, D2 and D6).
 *
 * A chat turn that ends on a held command asks this ledger for a token. The token is 32 random
 * bytes, handed out once in the `approval_required` event and kept here only as its SHA-256, bound
 * to four things: the verified principal, the conversation, the tool call, and the hash of the
 * exact command (pathKey, params, positionals). An answer redeems the token once:
 *
 *   - an unknown token (forged, already spent, or expired) and a token presented by another
 *     principal, conversation or tool call answer the same `AI_APPROVAL_UNKNOWN`, so a probe learns
 *     nothing about whose token it guessed;
 *   - a token presented with another command answers `AI_APPROVAL_COMMAND_MISMATCH` and stays
 *     pending, so a tampered answer cannot burn the real one;
 *   - a matching answer spends the token. An approval leaves one grant for that exact command in
 *     that conversation, which the next tool call naming the same argv consumes to run once with
 *     the confirmation granted (tools.ts); a rejection leaves nothing.
 *
 * Everything is RAM only: an executor restart forgets every pending token and grant, which fails
 * closed (the page asks again).
 */

import { createHash, randomBytes, timingSafeEqual } from 'node:crypto';
import type { AiApprovalCommand } from '@rediacc/shared/cli-contract/wire';
import type { AiApprovalSubmit, AiApprovalVerdict } from '../serve/ai-routes.js';
import type { SessionPrincipal } from '../serve/sessions.js';

/** How long a pending approval waits for its answer, and how long an approved grant waits for its run. */
export const APPROVAL_TTL_MS = 15 * 60 * 1000;

/** Pending approvals kept at once; the oldest is dropped beyond this. */
const MAX_PENDING = 10_000;

/** Pending approvals one principal keeps; its own oldest is dropped beyond this, so it cannot push out another's. */
const MAX_PENDING_PER_PRINCIPAL = 100;

export const AI_APPROVAL_UNKNOWN = 'AI_APPROVAL_UNKNOWN';
export const AI_APPROVAL_COMMAND_MISMATCH = 'AI_APPROVAL_COMMAND_MISMATCH';

/** Bytes of entropy in one token. */
const TOKEN_BYTES = 32;

/** The value with its object keys sorted at every depth, so equal commands serialize equally. */
function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === 'object') {
    const sorted: Record<string, unknown> = {};
    // Object keys are distinct, so the comparison never sees two equal keys.
    for (const key of Object.keys(value).sort((a, b) => (a < b ? -1 : 1))) {
      const inner = (value as Record<string, unknown>)[key];
      if (inner !== undefined) sorted[key] = canonical(inner);
    }
    return sorted;
  }
  return value;
}

/** The SHA-256 (hex) of a command's canonical argv: what a token and a grant are bound to. */
export function argvHashOf(command: AiApprovalCommand): string {
  const { pathKey, params, positionals } = command;
  return createHash('sha256')
    .update(JSON.stringify(canonical({ pathKey, params, positionals })))
    .digest('hex');
}

const principalKeyOf = (principal: SessionPrincipal): string =>
  `${principal.orgId}\u0000${principal.userId}`;

const sha256 = (text: string): Buffer => createHash('sha256').update(text).digest();

interface PendingApproval {
  principalKey: string;
  conversationId: string;
  toolCallId: string;
  argvHash: string;
  expiresAtMs: number;
}

/** The ledger seam the routes and the chat tools use. */
export interface AiApprovals {
  /** Issue the single-use token of one held tool call. */
  issue(
    principal: SessionPrincipal,
    conversationId: string,
    toolCallId: string,
    command: AiApprovalCommand
  ): string;
  /** Redeem one answer: verify the token's bindings, spend it, and grant an approved command once. */
  submit(answer: AiApprovalSubmit): Promise<AiApprovalVerdict>;
  /** Consume the grant an approval left for exactly this command; false when there is none. */
  takeGrant(
    principal: SessionPrincipal,
    conversationId: string,
    command: AiApprovalCommand
  ): boolean;
  /** Withdraw a grant whose approval could not be recorded (approval-audit.ts). */
  revokeGrant(
    principal: SessionPrincipal,
    conversationId: string,
    command: AiApprovalCommand
  ): void;
}

export class AiApprovalLedger implements AiApprovals {
  /** Pending approvals by the hex SHA-256 of their token. */
  private readonly pending = new Map<string, PendingApproval>();
  /** Approved grants by (principal, conversation, argv hash), with their expiry. */
  private readonly grants = new Map<string, number>();

  constructor(private readonly now: () => number = Date.now) {}

  private sweep(): void {
    const now = this.now();
    for (const [key, entry] of this.pending) if (entry.expiresAtMs <= now) this.pending.delete(key);
    for (const [key, expiresAtMs] of this.grants) if (expiresAtMs <= now) this.grants.delete(key);
  }

  private grantKey(
    principal: SessionPrincipal,
    conversationId: string,
    command: AiApprovalCommand
  ): string {
    return `${principalKeyOf(principal)}\u0000${conversationId}\u0000${argvHashOf(command)}`;
  }

  /** Make room for one more pending approval of `principalKey` under its own cap. */
  private dropOldestOf(principalKey: string): void {
    let count = 0;
    let oldest: string | undefined;
    for (const [key, entry] of this.pending) {
      if (entry.principalKey !== principalKey) continue;
      oldest ??= key;
      count += 1;
    }
    if (count >= MAX_PENDING_PER_PRINCIPAL && oldest !== undefined) this.pending.delete(oldest);
  }

  issue(
    principal: SessionPrincipal,
    conversationId: string,
    toolCallId: string,
    command: AiApprovalCommand
  ): string {
    this.sweep();
    this.dropOldestOf(principalKeyOf(principal));
    if (this.pending.size >= MAX_PENDING) {
      const oldest = this.pending.keys().next().value;
      if (oldest !== undefined) this.pending.delete(oldest);
    }
    const token = randomBytes(TOKEN_BYTES).toString('base64url');
    this.pending.set(sha256(token).toString('hex'), {
      principalKey: principalKeyOf(principal),
      conversationId,
      toolCallId,
      argvHash: argvHashOf(command),
      expiresAtMs: this.now() + APPROVAL_TTL_MS,
    });
    return token;
  }

  submit(answer: AiApprovalSubmit): Promise<AiApprovalVerdict> {
    this.sweep();
    const key = sha256(answer.approvalToken).toString('hex');
    const entry = this.pending.get(key);
    const bound =
      entry !== undefined &&
      entry.principalKey === principalKeyOf(answer.principal) &&
      entry.conversationId === answer.conversationId &&
      entry.toolCallId === answer.toolCallId;
    if (!bound) {
      return Promise.resolve({
        ok: false,
        status: 404,
        code: AI_APPROVAL_UNKNOWN,
        message: 'No approval is pending for this token.',
      });
    }
    const presented = Buffer.from(argvHashOf(answer.command), 'hex');
    if (!timingSafeEqual(presented, Buffer.from(entry.argvHash, 'hex'))) {
      return Promise.resolve({
        ok: false,
        status: 409,
        code: AI_APPROVAL_COMMAND_MISMATCH,
        message: 'The answer names another command than the one the model asked to run.',
      });
    }
    this.pending.delete(key);
    if (answer.decision === 'approve') {
      const grant = this.grantKey(answer.principal, answer.conversationId, answer.command);
      this.grants.set(grant, this.now() + APPROVAL_TTL_MS);
    }
    return Promise.resolve({ ok: true });
  }

  takeGrant(
    principal: SessionPrincipal,
    conversationId: string,
    command: AiApprovalCommand
  ): boolean {
    this.sweep();
    return this.grants.delete(this.grantKey(principal, conversationId, command));
  }

  revokeGrant(
    principal: SessionPrincipal,
    conversationId: string,
    command: AiApprovalCommand
  ): void {
    this.grants.delete(this.grantKey(principal, conversationId, command));
  }
}
