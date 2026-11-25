/**
 * The AI conversation recorder (D7, D8 of agent/plans/PLAN-console-ai-assistant.md): each message
 * sealed under the session key and posted with its parent id and seq, in order per conversation,
 * and an unreachable account route that never fails the turn.
 */

import { openAiMessage, openAiTitle } from '@rediacc/shared/ai/seal';
import { randomBytes } from '@rediacc/shared/config-crypto';
import { describe, expect, it } from 'vitest';
import type { SessionPrincipal } from '../../serve/sessions.js';
import { AI_MESSAGE_ATTEMPTS, type AiMessageRecord, createAiRecorder } from '../recorder.js';

const PRINCIPAL: SessionPrincipal = {
  userId: 'user-1',
  orgId: 'org-1',
  teamId: 'team-1',
  userEmail: 'u@example.com',
  orgRole: 'owner',
  tokenId: 'tok-1',
};

const CEK = randomBytes(32);

interface Posted {
  conversationId: string;
  messageId: string;
  parentId: string | null;
  seq: number;
  body: string;
  cekGeneration: number;
  titleSealed?: string;
  onBehalfOfTokenId: string;
}

function capture(answer: () => Response | Promise<Response> = () => Response.json({ ok: true })) {
  const posted: Posted[] = [];
  const headers: Headers[] = [];
  let calls = 0;
  const fetchImpl = ((url: string | URL, init?: RequestInit) => {
    calls++;
    expect(String(url)).toBe('https://account.test/account/api/v1/console/ai/messages');
    posted.push(JSON.parse(init?.body as string) as Posted);
    headers.push(new Headers(init?.headers));
    return Promise.resolve(answer());
  }) as typeof fetch;
  return { posted, headers, fetchImpl, calls: () => calls };
}

function message(overrides: Partial<AiMessageRecord> = {}): AiMessageRecord {
  return {
    principal: PRINCIPAL,
    conversationId: 'conv-1',
    parentId: null,
    seq: 0,
    body: { role: 'user', text: 'list my machines' },
    cekGeneration: 2,
    cek: () => Promise.resolve(CEK),
    ...overrides,
  };
}

describe('AI conversation recorder', () => {
  it('posts a sealed message under the executor token that opens to the original body', async () => {
    const { posted, headers, fetchImpl } = capture();
    const recorder = createAiRecorder({
      accountUrl: 'https://account.test/',
      executorToken: 'rdt_executor',
      fetchImpl,
    });
    const outcome = await recorder.record(message({ messageId: 'm-1', title: 'Machines' }));

    expect(outcome).toEqual({ messageId: 'm-1', delivered: true });
    expect(headers[0]?.get('authorization')).toBe('Bearer rdt_executor');
    const [sent] = posted;
    expect(new Set(Object.keys(sent ?? {}))).toEqual(
      new Set([
        'body',
        'cekGeneration',
        'conversationId',
        'messageId',
        'onBehalfOfTokenId',
        'parentId',
        'seq',
        'titleSealed',
      ])
    );
    expect(sent?.body).not.toContain('machines');
    expect(JSON.stringify(sent)).not.toContain('list my machines');
    expect(sent).toMatchObject({
      conversationId: 'conv-1',
      parentId: null,
      seq: 0,
      cekGeneration: 2,
      onBehalfOfTokenId: 'tok-1',
    });
    const ctx = { orgId: 'org-1', userId: 'user-1', conversationId: 'conv-1', cekGeneration: 2 };
    expect(await openAiMessage(CEK, ctx, 'm-1', sent?.body ?? '')).toEqual({
      role: 'user',
      text: 'list my machines',
    });
    expect(await openAiTitle(CEK, ctx, sent?.titleSealed ?? '')).toBe('Machines');
  });

  it('carries the parent id and seq of a reply and of a sibling branch', async () => {
    const { posted, fetchImpl } = capture();
    const recorder = createAiRecorder({
      accountUrl: 'https://account.test',
      executorToken: 't',
      fetchImpl,
    });
    const root = await recorder.record(message({ messageId: 'm-1' }));
    await recorder.record(
      message({
        messageId: 'm-2',
        parentId: root.messageId,
        seq: 1,
        body: {
          role: 'assistant',
          text: 'one',
          runs: [{ toolCallId: 'c', runId: 'r', pathKey: 'machine list' }],
        },
      })
    );
    await recorder.record(
      message({
        messageId: 'm-3',
        parentId: root.messageId,
        seq: 2,
        body: { role: 'assistant', text: 'two' },
      })
    );
    expect(posted.map((p) => [p.messageId, p.parentId, p.seq])).toEqual([
      ['m-1', null, 0],
      ['m-2', 'm-1', 1],
      ['m-3', 'm-1', 2],
    ]);
  });

  it('delivers the messages of one conversation in order even when the first answers slowly', async () => {
    const order: string[] = [];
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fetchImpl = (async (_url: string | URL, init?: RequestInit) => {
      const { messageId } = JSON.parse(init?.body as string) as Posted;
      if (messageId === 'm-1') await gate;
      order.push(messageId);
      return Response.json({ ok: true });
    }) as typeof fetch;
    const recorder = createAiRecorder({
      accountUrl: 'https://account.test',
      executorToken: 't',
      fetchImpl,
    });
    const first = recorder.record(message({ messageId: 'm-1' }));
    const second = recorder.record(message({ messageId: 'm-2', parentId: 'm-1', seq: 1 }));
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(order).toEqual([]);
    release();
    await Promise.all([first, second]);
    expect(order).toEqual(['m-1', 'm-2']);
  });

  it('never fails the turn when the account route is unreachable, after the retry budget', async () => {
    const failures: string[] = [];
    const fetchImpl = (() => Promise.reject(new TypeError('fetch failed'))) as typeof fetch;
    let calls = 0;
    const counting = ((url: string | URL, init?: RequestInit) => {
      calls++;
      return fetchImpl(url, init);
    }) as typeof fetch;
    const recorder = createAiRecorder({
      accountUrl: 'https://account.test',
      executorToken: 't',
      fetchImpl: counting,
      onFailure: (reason) => failures.push(reason),
    });
    await expect(recorder.record(message({ messageId: 'm-1' }))).resolves.toEqual({
      messageId: 'm-1',
      delivered: false,
    });
    expect(calls).toBe(AI_MESSAGE_ATTEMPTS);
    expect(failures).toEqual(['fetch failed']);
  });

  it('retries a 503 and stops at a 409 refusal without retrying', async () => {
    const statuses = [503, 200];
    const retried = capture(() => new Response('{}', { status: statuses.shift() ?? 200 }));
    const recorder = createAiRecorder({
      accountUrl: 'https://account.test',
      executorToken: 't',
      fetchImpl: retried.fetchImpl,
    });
    expect((await recorder.record(message())).delivered).toBe(true);
    expect(retried.calls()).toBe(2);

    const failures: string[] = [];
    const refused = capture(() => Response.json({ code: 'AI_PARENT_MISSING' }, { status: 409 }));
    const strict = createAiRecorder({
      accountUrl: 'https://account.test',
      executorToken: 't',
      fetchImpl: refused.fetchImpl,
      onFailure: (reason) => failures.push(reason),
    });
    expect((await strict.record(message())).delivered).toBe(false);
    expect(refused.calls()).toBe(1);
    expect(failures[0]).toContain('409');
  });

  it('posts nothing for a session without a config key, a principal without a token, or a throwing reporter', async () => {
    const { calls, fetchImpl } = capture();
    const failures: string[] = [];
    const recorder = createAiRecorder({
      accountUrl: 'https://account.test',
      executorToken: 't',
      fetchImpl,
      onFailure: (reason) => {
        failures.push(reason);
        throw new Error('reporter broke');
      },
    });
    const noKey = await recorder.record(message({ cek: () => Promise.resolve(undefined) }));
    const keyThrows = await recorder.record(
      message({ conversationId: 'conv-2', cek: () => Promise.reject(new Error('session gone')) })
    );
    const { tokenId: _dropped, ...withoutToken } = PRINCIPAL;
    const noToken = await recorder.record(
      message({ conversationId: 'conv-3', principal: withoutToken })
    );
    expect([noKey.delivered, keyThrows.delivered, noToken.delivered]).toEqual([
      false,
      false,
      false,
    ]);
    expect(calls()).toBe(0);
    expect(failures).toHaveLength(3);
  });

  it('reports a body the store would refuse instead of throwing', async () => {
    const { calls, fetchImpl } = capture();
    const failures: string[] = [];
    const recorder = createAiRecorder({
      accountUrl: 'https://account.test',
      executorToken: 't',
      fetchImpl,
      onFailure: (reason) => failures.push(reason),
    });
    const outcome = await recorder.record(
      message({ body: { role: 'user', text: 'x'.repeat(70 * 1024) } })
    );
    expect(outcome.delivered).toBe(false);
    expect(calls()).toBe(0);
    expect(failures[0]).toContain('could not be sealed');
  });
});
