import { describe, expect, it } from 'vitest';
import type { ExecutorAuditEvent } from '../../serve/deps.js';
import type { SessionPrincipal } from '../../serve/sessions.js';
import {
  auditApproval,
  auditJudgeVerdict,
  auditJudgment,
  auditModeChange,
  auditRefusal,
} from '../approval-audit.js';

const principal: SessionPrincipal = {
  orgId: 'org-1',
  teamId: null,
  userId: 'user-1',
  userEmail: 'a@example.com',
  orgRole: 'owner',
};

function sink() {
  const events: ExecutorAuditEvent[] = [];
  return {
    events,
    audit: (event: ExecutorAuditEvent) => {
      events.push(event);
      return Promise.resolve();
    },
  };
}

describe('AI decision audit events', () => {
  it('records an approval as success and a rejection as failure, with the request id', async () => {
    const { events, audit } = sink();
    const base = { principal, destructive: true, requestId: 'c1:t1' };
    await auditApproval(audit, { ...base, decision: 'approve' });
    await auditApproval(audit, { ...base, decision: 'reject' });
    expect(events.map((e) => [e.commandPath, e.success, e.requestId])).toEqual([
      ['ai approval', true, 'c1:t1'],
      ['ai approval', false, 'c1:t1'],
    ]);
    expect(events[0]?.destructive).toBe(true);
  });

  it('records a judge verdict: an allow succeeds, a block fails', async () => {
    const { events, audit } = sink();
    await auditJudgeVerdict(audit, { principal, destructive: false, verdict: 'allow' });
    await auditJudgeVerdict(audit, { principal, destructive: true, verdict: 'block' });
    expect(events.map((e) => [e.commandPath, e.success, e.exitCode, e.destructive])).toEqual([
      ['ai judge', true, 0, false],
      ['ai judge', false, 1, true],
    ]);
  });

  it('records a refusal as a failure under its own path', async () => {
    const { events, audit } = sink();
    await auditRefusal(audit, { principal, destructive: true, requestId: 'c1:t2' });
    expect(events).toMatchObject([
      { commandPath: 'ai refusal', success: false, exitCode: 1, requestId: 'c1:t2' },
    ]);
  });

  it('names the decided command in the path of an approval, a judge verdict and a refusal', async () => {
    const { events, audit } = sink();
    const base = { principal, destructive: false, requestId: 'c1:t1', pathKey: 'repo up' };
    await auditApproval(audit, { ...base, decision: 'approve' });
    await auditJudgeVerdict(audit, { ...base, verdict: 'block' });
    await auditRefusal(audit, base);
    await auditModeChange(audit, { ...base, mode: 'ask' });
    expect(events.map((e) => e.commandPath)).toEqual([
      'ai approval repo up',
      'ai judge repo up',
      'ai refusal repo up',
      'ai mode ask',
    ]);
  });

  it('leaves out a pathKey that is too long or shaped like a parameter, never truncating it', async () => {
    const { events, audit } = sink();
    const base = { principal, destructive: false, requestId: 'c1:t1' };
    const long = Array.from({ length: 40 }, (_, i) => `word${i}`).join(' ');
    const ok = 'repo up';
    await auditRefusal(audit, { ...base, pathKey: long });
    await auditRefusal(audit, { ...base, pathKey: 'repo up --password hunter2' });
    await auditRefusal(audit, { ...base, pathKey: 'repo up\nshop' });
    await auditRefusal(audit, { ...base, pathKey: 'repo up hunter2-secret' });
    await auditRefusal(audit, { ...base, pathKey: 'repo up -x' });
    await auditRefusal(audit, { ...base, pathKey: 'repo up--x' });
    await auditRefusal(audit, { ...base, pathKey: ok });
    expect(events.map((e) => e.commandPath)).toEqual([
      'ai refusal',
      'ai refusal',
      'ai refusal',
      'ai refusal',
      'ai refusal',
      'ai refusal',
      'ai refusal repo up',
    ]);
    expect(long.length + 'ai refusal '.length).toBeGreaterThan(200);
  });

  it('emits no sensitive option value in any event, however the pathKey carries it', async () => {
    const { events, audit } = sink();
    const secret = 'hunter2-secret';
    const base = { principal, destructive: true, requestId: 'c1:t1' };
    const keys = [`repo up --password ${secret}`, `repo up=${secret}`, 'repo up'];
    for (const pathKey of keys) {
      await auditApproval(audit, { ...base, decision: 'approve', pathKey });
      await auditJudgeVerdict(audit, { ...base, verdict: 'allow', pathKey });
      await auditRefusal(audit, { ...base, pathKey });
      await auditModeChange(audit, { ...base, mode: 'ask', pathKey });
    }
    expect(events).toHaveLength(12);
    expect(JSON.stringify(events)).not.toContain(secret);
  });

  it('records a mode change under the new mode and ships no params', async () => {
    const { events, audit } = sink();
    await auditModeChange(audit, { principal, destructive: false, mode: 'skip' });
    expect(events).toMatchObject([{ commandPath: 'ai mode skip', success: true, params: {} }]);
    expect(events[0]).not.toHaveProperty('requestId');
  });

  it('joins a judge verdict and its fallback mode change by the tool call request id', async () => {
    const { events, audit } = sink();
    const call = { entry: { severity: 'destructive' }, command: { pathKey: 'repo up' } };
    await auditJudgment(audit, {
      principal,
      requestId: 'c1:t9',
      call: call as never,
      judgment: { verdict: { verdict: 'block' }, fallback: {} },
    });
    expect(events.map((e) => [e.commandPath, e.requestId])).toEqual([
      ['ai judge repo up', 'c1:t9'],
      ['ai mode ask', 'c1:t9'],
    ]);
  });

  it('does nothing when no sink is configured, and passes a sink failure through', async () => {
    await expect(
      auditJudgeVerdict(undefined, { principal, destructive: false, verdict: 'allow' })
    ).resolves.toBeUndefined();
    await expect(
      auditRefusal(() => Promise.reject(new Error('sink down')), { principal, destructive: false })
    ).rejects.toThrow('sink down');
  });
});
