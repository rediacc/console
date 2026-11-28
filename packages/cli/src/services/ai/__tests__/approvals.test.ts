/**
 * The single-use approval token (AI3 of agent/plans/PLAN-console-ai-assistant.md): bound to the
 * principal, the conversation, the tool call and the argv hash, spent on its first matching answer,
 * and leaving exactly one grant behind an approval.
 */

import { describe, expect, it } from 'vitest';
import type { AiApprovalSubmit } from '../../serve/ai-routes.js';
import {
  AI_APPROVAL_COMMAND_MISMATCH,
  AI_APPROVAL_UNKNOWN,
  AiApprovalLedger,
  APPROVAL_TTL_MS,
  argvHashOf,
} from '../approvals.js';

const principal = {
  orgId: 'org-1',
  teamId: null,
  userId: 'user-owner',
  userEmail: 'owner@example.com',
  orgRole: 'owner' as const,
};

const DELETE_SHOP = { pathKey: 'repo delete', params: {}, positionals: { ref: 'shop' } };

function issued(ledger = new AiApprovalLedger()) {
  const token = ledger.issue(principal, 'conv-1', 'call-1', DELETE_SHOP);
  return { ledger, token };
}

const answer = (token: string, over: Partial<AiApprovalSubmit> = {}): AiApprovalSubmit => ({
  principal,
  conversationId: 'conv-1',
  toolCallId: 'call-1',
  approvalToken: token,
  decision: 'approve',
  command: DELETE_SHOP,
  stepUpMethod: 'passkey',
  destructive: true,
  grand: true,
  ...over,
});

describe('AiApprovalLedger', () => {
  it('issues a fresh 256-bit token per call', () => {
    const ledger = new AiApprovalLedger();
    const a = ledger.issue(principal, 'conv-1', 'call-1', DELETE_SHOP);
    const b = ledger.issue(principal, 'conv-1', 'call-1', DELETE_SHOP);
    expect(a).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(a).not.toBe(b);
  });

  it('refuses a forged token', async () => {
    const { ledger } = issued();
    const forged = await ledger.submit(answer('A'.repeat(43)));
    expect(forged).toMatchObject({ ok: false, status: 404, code: AI_APPROVAL_UNKNOWN });
    expect(ledger.takeGrant(principal, 'conv-1', DELETE_SHOP)).toBe(false);
  });

  it('refuses a reused token', async () => {
    const { ledger, token } = issued();
    expect(await ledger.submit(answer(token))).toEqual({ ok: true });
    expect(await ledger.submit(answer(token))).toMatchObject({
      ok: false,
      status: 404,
      code: AI_APPROVAL_UNKNOWN,
    });
  });

  it('refuses a token for another command, and keeps it pending for its own', async () => {
    const { ledger, token } = issued();
    const other = { pathKey: 'repo delete', params: {}, positionals: { ref: 'shop:trial' } };
    expect(await ledger.submit(answer(token, { command: other }))).toMatchObject({
      ok: false,
      status: 409,
      code: AI_APPROVAL_COMMAND_MISMATCH,
    });
    expect(ledger.takeGrant(principal, 'conv-1', other)).toBe(false);
    expect(await ledger.submit(answer(token))).toEqual({ ok: true });
  });

  it('refuses a token presented by another principal, conversation or tool call alike', async () => {
    const { ledger, token } = issued();
    const strangers: Partial<AiApprovalSubmit>[] = [
      { principal: { ...principal, userId: 'user-other' } },
      { principal: { ...principal, orgId: 'org-2' } },
      { conversationId: 'conv-2' },
      { toolCallId: 'call-2' },
    ];
    for (const over of strangers) {
      expect(await ledger.submit(answer(token, over))).toMatchObject({
        ok: false,
        status: 404,
        code: AI_APPROVAL_UNKNOWN,
      });
    }
    expect(await ledger.submit(answer(token))).toEqual({ ok: true });
  });

  it('leaves one grant behind an approval, for that exact argv and conversation only', async () => {
    const { ledger, token } = issued();
    await ledger.submit(answer(token));
    expect(ledger.takeGrant(principal, 'conv-2', DELETE_SHOP)).toBe(false);
    expect(ledger.takeGrant({ ...principal, userId: 'user-other' }, 'conv-1', DELETE_SHOP)).toBe(
      false
    );
    expect(ledger.takeGrant(principal, 'conv-1', DELETE_SHOP)).toBe(true);
    expect(ledger.takeGrant(principal, 'conv-1', DELETE_SHOP)).toBe(false);
  });

  it('leaves no grant behind a rejection, and a revoked grant is gone', async () => {
    const rejected = issued();
    await rejected.ledger.submit(answer(rejected.token, { decision: 'reject' }));
    expect(rejected.ledger.takeGrant(principal, 'conv-1', DELETE_SHOP)).toBe(false);

    const revoked = issued();
    await revoked.ledger.submit(answer(revoked.token));
    revoked.ledger.revokeGrant(principal, 'conv-1', DELETE_SHOP);
    expect(revoked.ledger.takeGrant(principal, 'conv-1', DELETE_SHOP)).toBe(false);
  });

  it('forgets a pending token and an unused grant after the window', async () => {
    let now = 0;
    const clock = () => now;
    const pending = issued(new AiApprovalLedger(clock));
    now = APPROVAL_TTL_MS + 1;
    expect(await pending.ledger.submit(answer(pending.token))).toMatchObject({ status: 404 });

    now = 0;
    const granted = issued(new AiApprovalLedger(clock));
    await granted.ledger.submit(answer(granted.token));
    now = APPROVAL_TTL_MS + 1;
    expect(granted.ledger.takeGrant(principal, 'conv-1', DELETE_SHOP)).toBe(false);
  });
});

describe('argvHashOf', () => {
  it('ignores key order and separates every field', () => {
    const a = { pathKey: 'repo up', params: { a: 1, b: 2 }, positionals: { ref: 'x' } };
    const b = { pathKey: 'repo up', params: { b: 2, a: 1 }, positionals: { ref: 'x' } };
    expect(argvHashOf(a)).toBe(argvHashOf(b));
    expect(argvHashOf(a)).not.toBe(argvHashOf({ ...a, positionals: { ref: 'y' } }));
    expect(argvHashOf(a)).not.toBe(argvHashOf({ ...a, params: { a: 1, b: 3 } }));
    expect(argvHashOf(a)).not.toBe(argvHashOf({ ...a, pathKey: 'repo down' }));
  });

  it('keeps one principal from pushing out another principal pending approval', async () => {
    const ledger = new AiApprovalLedger();
    const other = { ...principal, userId: 'user-other' };
    const otherToken = ledger.issue(other, 'conv-1', 'call-1', DELETE_SHOP);
    const first = ledger.issue(principal, 'conv-1', 'call-1', DELETE_SHOP);
    // 100 is the per-principal cap: the 101st of one principal drops that principal's own oldest.
    for (let i = 0; i < 100; i += 1)
      ledger.issue(principal, 'conv-1', `call-${i + 2}`, DELETE_SHOP);
    expect(await ledger.submit(answer(first))).toMatchObject({ code: AI_APPROVAL_UNKNOWN });
    expect(await ledger.submit(answer(otherToken, { principal: other }))).toEqual({ ok: true });
  });

  it('frees a cap slot when a pending approval is answered', async () => {
    const ledger = new AiApprovalLedger();
    const tokens: string[] = [];
    for (let i = 0; i < 100; i += 1)
      tokens.push(ledger.issue(principal, 'conv-1', `call-${i}`, DELETE_SHOP));
    const [oldest, second] = tokens as [string, string];
    expect(await ledger.submit(answer(second, { toolCallId: 'call-1' }))).toEqual({ ok: true });
    ledger.issue(principal, 'conv-1', 'call-100', DELETE_SHOP);
    // The answered slot was free, so the oldest survives the 101st issue.
    expect(await ledger.submit(answer(oldest, { toolCallId: 'call-0' }))).toEqual({ ok: true });
  });
});
