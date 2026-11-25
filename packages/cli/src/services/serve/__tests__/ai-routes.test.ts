/**
 * The executor's AI mode and approval routes (AI5 of agent/plans/PLAN-console-ai-assistant.md).
 *
 * The mode route refuses a mode the policy disabled (D6). The approval route resolves the target
 * itself and refuses an approval of a destructive command or a grand-repo target that arrives
 * without the step-up method the account must have checked (C12, C13), whatever the browser said
 * about `grand`; the single-use token goes to the loop's approval ledger, whose refusal passes
 * through. The real contract, policy code and repo resolver run; the account server is faked.
 */

import type { AiConfig, Profile } from '@rediacc/shared/ai';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import type { PolicyDocument } from '@rediacc/shared/policy';
import { simulateReadableStream } from 'ai';
import { MockLanguageModelV4 } from 'ai/test';
import { Hono } from 'hono';
import { beforeEach, describe, expect, it, vi } from 'vitest';

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-ai-routes-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

import { AiApprovalLedger, MAX_TOOL_STEPS, STEP_LIMIT_REASON } from '../../ai/loop.js';
import { type AgentGrantHandle, AgentSessionRefused } from '../agent-grant-session.js';
import {
  AI_APPROVAL_STEPUP_REQUIRED,
  AI_GRANT_UNAVAILABLE,
  AI_MODE_DISABLED,
  AI_PROFILE_UNRESOLVED,
  AI_ROUTES,
  type AiApprovalSubmit,
  type AiApprovalVerdict,
  type AiChatDeps,
  type AiMode,
  registerAiRoutes,
} from '../ai-routes.js';
import { AuthError, AuthVerifier } from '../auth.js';
import { CommandRejected } from '../command-dispatch.js';
import { serveCrypto } from '../crypto.js';
import type { ServeDeps } from '../deps.js';
import { authorize } from '../policy.js';
import { SessionStore } from '../sessions.js';

const OWNER_TOKEN = 'rdt_owner';
const GRAND_GUID = '11111111-1111-4111-8111-111111111111';
const FORK_GUID = '22222222-2222-4222-8222-222222222222';

const OWNER = {
  active: true,
  scopes: ['proxy:exec'],
  orgId: 'org-1',
  teamId: null,
  createdByUserId: 'user-owner',
  userEmail: 'owner@example.com',
  orgRole: 'owner',
};

/** `shop` is a grand repo (tag latest); `shop:trial` is a fork of it. */
function fleetConfig(policy?: PolicyDocument): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000000cc',
    version: 1,
    credentials: { ssh: { privateKey: 'KEY' } },
    resources: {
      machines: { m1: { ip: '10.1.1.1', user: 'root', port: 22 } },
      repositories: {
        shop: {
          grand: 'latest',
          placement: { machine: 'm1' },
          tags: {
            latest: { repositoryGuid: GRAND_GUID },
            trial: { repositoryGuid: FORK_GUID, grandGuid: GRAND_GUID, parentGuid: GRAND_GUID },
          },
        },
      },
    },
    state: { repos: { shop: { latest: { networkId: 2816 }, trial: { networkId: 2880 } } } },
    encryption: { mode: 'plaintext' },
    ...(policy ? { policy } : {}),
  };
}

const fakeAccount = ((_url: string | URL, init?: RequestInit) => {
  const { token } = JSON.parse(String(init?.body ?? '{}')) as { token: string };
  return Promise.resolve(Response.json(token === OWNER_TOKEN ? OWNER : { active: false }));
}) as typeof fetch;

/** The status mapping server.ts lends, reduced to the errors these routes can meet. */
function statusFor(error: unknown) {
  if (error instanceof AuthError) return { status: error.status, message: error.message };
  if (error instanceof CommandRejected) return { status: 400 as const, message: error.message };
  return { status: 500 as const, message: error instanceof Error ? error.message : 'failed' };
}

let modes: { conversationId: string; mode: AiMode }[];
let submitted: AiApprovalSubmit[];
let verdict: AiApprovalVerdict;

interface AppOptions {
  chat?: AiChatDeps;
  authorize?: ServeDeps['authorize'];
  agentGrants?: ServeDeps['agentGrants'];
}

function app(config: RdcConfig, options: AppOptions = {}): Hono {
  const deps: ServeDeps = {
    mode: 'container',
    auth: new AuthVerifier({
      accountUrl: 'https://account.test',
      executorToken: 'rdt_executor',
      fetchImpl: fakeAccount,
    }),
    sessions: new SessionStore(),
    crypto: serveCrypto,
    executor: { execute: () => Promise.reject(new Error('the approval route runs nothing')) },
    loadConfig: () => Promise.resolve(config),
    authorize: options.authorize ?? authorize,
    ...(options.agentGrants ? { agentGrants: options.agentGrants } : {}),
  };
  const hono = new Hono();
  registerAiRoutes(
    hono,
    deps,
    {
      authenticate: (header) => {
        const token = header?.replace(/^Bearer\s+/i, '').trim() ?? '';
        if (!token) return Promise.reject(new AuthError('no token', 401));
        return deps.auth.verify(token);
      },
      statusFor,
      requestScopedConfig: (c) => c,
      withRequestConfig: (_c, fn) => fn(),
      configSession: (header) => header?.trim() || undefined,
    },
    {
      modes: { set: (_p, conversationId, mode) => modes.push({ conversationId, mode }) },
      approvals: {
        submit: (answer) => {
          submitted.push(answer);
          return Promise.resolve(verdict);
        },
        expect: () => undefined,
      },
      ...(options.chat ? { chat: options.chat } : {}),
    }
  );
  return hono;
}

async function post(hono: Hono, route: string, body: unknown, token = OWNER_TOKEN) {
  const response = await hono.request(route, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  return { status: response.status, body: (await response.json()) as Record<string, unknown> };
}

function approval(
  pathKey: string,
  ref: string,
  extra: { decision?: 'approve' | 'reject'; stepUpMethod?: string | null; params?: object } = {}
) {
  return {
    conversationId: 'conv-1',
    toolCallId: 'call-1',
    approvalToken: 'tok-single-use',
    decision: extra.decision ?? 'approve',
    command: { pathKey, params: extra.params ?? {}, positionals: { ref } },
    stepUpMethod: extra.stepUpMethod === undefined ? null : extra.stepUpMethod,
  };
}

beforeEach(() => {
  modes = [];
  submitted = [];
  verdict = { ok: true };
});

describe('POST /v1/ai/mode', () => {
  it('accepts every mode under no policy and records it for the conversation', async () => {
    const hono = app(fleetConfig());
    for (const mode of ['ask', 'auto', 'skip'] as const) {
      const answer = await post(hono, AI_ROUTES.mode, { conversationId: 'conv-1', mode });
      expect(answer).toEqual({ status: 200, body: { conversationId: 'conv-1', mode } });
    }
    expect(modes.map((m) => m.mode)).toEqual(['ask', 'auto', 'skip']);
  });

  it('refuses a mode the org policy disabled and leaves the stored mode alone', async () => {
    const hono = app(
      fleetConfig({
        version: 1,
        defaults: { commands: { allow: ['*'] }, aiModesDisabled: ['auto'] },
      })
    );
    const refused = await post(hono, AI_ROUTES.mode, { conversationId: 'conv-1', mode: 'auto' });
    expect(refused.status).toBe(403);
    expect(refused.body).toMatchObject({ code: AI_MODE_DISABLED, disabled: ['auto'] });
    const allowed = await post(hono, AI_ROUTES.mode, { conversationId: 'conv-1', mode: 'skip' });
    expect(allowed.status).toBe(200);
    expect(modes).toEqual([{ conversationId: 'conv-1', mode: 'skip' }]);
  });

  it('refuses an unknown mode, an extra field and a caller without a token', async () => {
    const hono = app(fleetConfig());
    expect((await post(hono, AI_ROUTES.mode, { conversationId: 'c', mode: 'yolo' })).status).toBe(
      400
    );
    expect(
      (await post(hono, AI_ROUTES.mode, { conversationId: 'c', mode: 'ask', userId: 'x' })).status
    ).toBe(400);
    expect(
      (await post(hono, AI_ROUTES.mode, { conversationId: 'c', mode: 'ask' }, '')).status
    ).toBe(401);
    expect(modes).toEqual([]);
  });
});

describe('POST /v1/ai/approval', () => {
  it('passes a caution command on a fork to the ledger without a step-up', async () => {
    const answer = await post(
      app(fleetConfig()),
      AI_ROUTES.approval,
      approval('repo up', 'shop:trial')
    );
    expect(answer).toEqual({
      status: 200,
      body: {
        conversationId: 'conv-1',
        toolCallId: 'call-1',
        decision: 'approve',
        stepUpMethod: null,
      },
    });
    expect(submitted).toHaveLength(1);
    expect(submitted[0]).toMatchObject({
      approvalToken: 'tok-single-use',
      grand: false,
      destructive: false,
      principal: { userId: 'user-owner', orgId: 'org-1' },
    });
  });

  it('refuses approving a grand-repo target without a step-up, whatever the account judged', async () => {
    const answer = await post(app(fleetConfig()), AI_ROUTES.approval, approval('repo up', 'shop'));
    expect(answer.status).toBe(403);
    expect(answer.body).toMatchObject({ code: AI_APPROVAL_STEPUP_REQUIRED, grand: true });
    expect(String(answer.body.error)).toContain('grand repo "shop"');
    expect(submitted).toEqual([]);
  });

  it('admits the grand-repo approval once a step-up method is named', async () => {
    const answer = await post(
      app(fleetConfig()),
      AI_ROUTES.approval,
      approval('repo up', 'shop', { stepUpMethod: 'passkey' })
    );
    expect(answer.status).toBe(200);
    expect(submitted[0]).toMatchObject({ grand: true, stepUpMethod: 'passkey' });
  });

  it('refuses approving a destructive command on a fork without a step-up, admits its dry run', async () => {
    const hono = app(fleetConfig());
    const refused = await post(hono, AI_ROUTES.approval, approval('repo down', 'shop:trial'));
    expect(refused.status).toBe(403);
    expect(refused.body).toMatchObject({ destructive: true, grand: false });
    const preview = await post(
      hono,
      AI_ROUTES.approval,
      approval('repo down', 'shop:trial', { params: { 'dry-run': true } })
    );
    expect(preview.status).toBe(200);
    expect(submitted).toHaveLength(1);
  });

  it('lets a rejection through without a step-up', async () => {
    const answer = await post(
      app(fleetConfig()),
      AI_ROUTES.approval,
      approval('repo delete', 'shop', { decision: 'reject' })
    );
    expect(answer.status).toBe(200);
    expect(submitted[0]).toMatchObject({ decision: 'reject', grand: true, destructive: true });
  });

  it("passes the ledger's refusal of a replayed token through", async () => {
    verdict = { ok: false, status: 409, code: 'AI_APPROVAL_TOKEN_SPENT', message: 'spent' };
    const answer = await post(
      app(fleetConfig()),
      AI_ROUTES.approval,
      approval('repo up', 'shop:trial')
    );
    expect(answer).toEqual({
      status: 409,
      body: { error: 'spent', code: 'AI_APPROVAL_TOKEN_SPENT' },
    });
  });

  it('refuses a body asserting grand, an unknown step-up method, and a non-proxyable command', async () => {
    const hono = app(fleetConfig());
    const asserted = { ...approval('repo up', 'shop'), grand: false };
    expect((await post(hono, AI_ROUTES.approval, asserted)).status).toBe(400);
    expect(
      (await post(hono, AI_ROUTES.approval, approval('repo up', 'shop', { stepUpMethod: 'sms' })))
        .status
    ).toBe(400);
    const config = await post(hono, AI_ROUTES.approval, {
      ...approval('config current', 'x'),
      command: { pathKey: 'config current', params: {}, positionals: {} },
    });
    expect(config.status).toBe(400);
    expect((await post(hono, AI_ROUTES.approval, approval('no such', 'x'))).status).toBe(400);
    expect(submitted).toEqual([]);
  });
});

type StreamPart =
  Awaited<ReturnType<MockLanguageModelV4['doStream']>>['stream'] extends ReadableStream<infer P>
    ? P
    : never;

const USAGE = {
  inputTokens: { total: 10, noCache: 10, cacheRead: undefined, cacheWrite: undefined },
  outputTokens: { total: 5, text: 5, reasoning: undefined },
};

function finish(unified: 'stop' | 'tool-calls'): StreamPart {
  return { type: 'finish', usage: USAGE, finishReason: { unified, raw: unified } };
}

function step(parts: StreamPart[]) {
  return {
    stream: simulateReadableStream({
      chunks: [{ type: 'stream-start', warnings: [] } as StreamPart, ...parts],
    }),
  };
}

function toolCallStep(toolName: string, input: Record<string, unknown>, id = 'call-1') {
  const json = JSON.stringify(input);
  return step([
    { type: 'tool-input-start', id, toolName },
    { type: 'tool-input-delta', id, delta: json },
    { type: 'tool-input-end', id },
    { type: 'tool-call', toolCallId: id, toolName, input: json },
    finish('tool-calls'),
  ]);
}

function textStep(text: string) {
  return step([
    { type: 'text-start', id: 't-1' },
    { type: 'text-delta', id: 't-1', delta: text },
    { type: 'text-end', id: 't-1' },
    finish('stop'),
  ]);
}

function profileOf(model: string): Profile {
  return {
    format: 'anthropic-messages',
    baseURL: 'https://api.anthropic.com',
    key: 'sk-test',
    authScheme: 'x-api-key',
    model,
    capabilities: { tools: true, streaming: true, parallelToolCalls: false, vision: false },
  };
}

function aiOf(model: string): AiConfig {
  return { providers: { main: profileOf(model) }, default: 'main' };
}

const CHAT = {
  conversationId: 'conv-1',
  messages: [{ role: 'user', content: 'bring shop up' }],
};

/** The lines of an NDJSON answer. */
async function lines(response: Response): Promise<Record<string, unknown>[]> {
  const text = await response.text();
  return text
    .split('\n')
    .filter(Boolean)
    .map((line) => JSON.parse(line) as Record<string, unknown>);
}

function chat(hono: Hono, body: unknown = CHAT, init: RequestInit = {}) {
  return hono.request(AI_ROUTES.chat, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${OWNER_TOKEN}` },
    body: JSON.stringify(body),
    ...init,
  });
}

function aiEvents(all: Record<string, unknown>[]) {
  return all.filter((l) => l.kind === 'ai').map((l) => l.ai as Record<string, unknown>);
}

function withAi(model: string): RdcConfig {
  return { ...fleetConfig(), ai: aiOf(model) };
}

describe('POST /v1/ai/chat', () => {
  it('caps a turn at 12 tool steps and ends it with the step-limit finish', async () => {
    let n = 0;
    const mock = new MockLanguageModelV4({
      doStream: () => {
        n += 1;
        return Promise.resolve(toolCallStep('repo_up', { ref: 'shop' }, `call-${n}`));
      },
    });
    const response = await chat(app(withAi('m'), { chat: { createModel: () => mock } }));
    expect(response.status).toBe(200);
    const events = aiEvents(await lines(response));
    expect(MAX_TOOL_STEPS).toBe(12);
    expect(mock.doStreamCalls).toHaveLength(12);
    expect(events.filter((e) => e.type === 'tool_result')).toHaveLength(12);
    expect(events.at(-1)).toEqual({ type: 'finish', reason: STEP_LIMIT_REASON });
  });

  it('stops the provider stream when the client aborts', async () => {
    let cancelled = false;
    const mock = new MockLanguageModelV4({
      doStream: () =>
        Promise.resolve({
          stream: new ReadableStream<StreamPart>({
            start(controller) {
              controller.enqueue({ type: 'stream-start', warnings: [] } as StreamPart);
              controller.enqueue({ type: 'text-start', id: 't-1' });
              controller.enqueue({ type: 'text-delta', id: 't-1', delta: 'thinking' });
            },
            cancel() {
              cancelled = true;
            },
          }),
        }),
    });
    const abort = new AbortController();
    const response = await chat(app(withAi('m'), { chat: { createModel: () => mock } }), CHAT, {
      signal: abort.signal,
    });
    const reader = (response.body as ReadableStream<Uint8Array>).getReader();
    const first = await reader.read();
    expect(new TextDecoder().decode(first.value)).toContain('text_delta');
    abort.abort();
    await vi.waitFor(() => expect(cancelled).toBe(true));
    expect(mock.doStreamCalls[0]?.abortSignal?.aborted).toBe(true);
  });

  it('runs every tool call as an agent, whatever kind or grant the body asserts', async () => {
    const seen: Parameters<typeof authorize>[0][] = [];
    const mock = new MockLanguageModelV4({
      doStream: [toolCallStep('repo_up', { ref: 'shop' }), textStep('Refused.')],
    });
    const response = await chat(
      app(withAi('m'), {
        chat: { createModel: () => mock },
        authorize: (args) => {
          seen.push(args);
          return authorize(args);
        },
      }),
      {
        ...CHAT,
        kind: 'human',
        principal: { userId: 'someone-else', orgRole: 'owner' },
        agentGrant: { allowGrandRepos: true, allowClusterOps: true },
      }
    );
    const events = aiEvents(await lines(response));
    expect(seen).toHaveLength(1);
    expect(seen[0]?.agentGrant).toEqual({ allowGrandRepos: false, allowClusterOps: false });
    expect(seen[0]?.principal.userId).toBe('user-owner');
    expect(events.find((e) => e.type === 'tool_result')).toMatchObject({
      ok: false,
      output: { status: 'refused' },
    });
  });

  it('uses the team profile over the shared one, and the shared one when the team has none', async () => {
    const used: string[] = [];
    const chatDeps = (configs: { team?: AiConfig; shared?: AiConfig }): AiChatDeps => ({
      aiConfigs: () => Promise.resolve(configs),
      createModel: (profile) => {
        used.push(profile.model);
        return new MockLanguageModelV4({ doStream: [textStep('hi')] });
      },
    });
    const both = { team: aiOf('team-model'), shared: aiOf('shared-model') };
    await (await chat(app(fleetConfig(), { chat: chatDeps(both) }))).text();
    await (
      await chat(app(fleetConfig(), { chat: chatDeps({ shared: aiOf('shared-model') }) }))
    ).text();
    expect(used).toEqual(['team-model', 'shared-model']);
  });

  it('answers 404 with a code when no profile is configured, and 401 without a token', async () => {
    const hono = app(fleetConfig());
    const none = await chat(hono);
    expect(none.status).toBe(404);
    expect(await none.json()).toMatchObject({ code: AI_PROFILE_UNRESOLVED });
    const noToken = await hono.request(AI_ROUTES.chat, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(CHAT),
    });
    expect(noToken.status).toBe(401);
  });

  it('refuses a malformed turn: the last message must be the user, and a grant is strict', async () => {
    const hono = app(withAi('m'));
    const assistantLast = await chat(hono, {
      ...CHAT,
      messages: [{ role: 'assistant', content: 'hi' }],
    });
    expect(assistantLast.status).toBe(400);
    const loose = await chat(hono, { ...CHAT, grant: { grantId: 'g1', secret: 's', extra: 1 } });
    expect(loose.status).toBe(400);
  });

  it('resolves a grant-bound chat inside the grant session, and passes its refusal through', async () => {
    const used: string[] = [];
    const handle: AgentGrantHandle = {
      grantId: 'g1',
      principal: {
        orgId: 'org-1',
        teamId: null,
        userId: 'agent-grant:g1',
        userEmail: 'agent-grant:g1',
        orgRole: 'member',
        agentGrantId: 'g1',
      },
      scope: { readOnly: false },
      overrides: { allowGrandRepos: ['shop'], allowClusterOps: false },
      config: {
        ...fleetConfig({
          version: 1,
          defaults: { commands: { allow: ['*'] }, allowGrandRepos: true },
        }),
        ai: aiOf('grant-model'),
      },
    };
    const seen: Parameters<typeof authorize>[0][] = [];
    const mock = new MockLanguageModelV4({
      doStream: [toolCallStep('repo_delete', { ref: 'shop' }), textStep('Asked.')],
    });
    const hono = app(withAi('caller-model'), {
      agentGrants: {
        acquire: (id: string) =>
          id === 'g1' ? Promise.resolve(handle) : Promise.reject(new AgentSessionRefused()),
      } as ServeDeps['agentGrants'],
      authorize: (args) => {
        seen.push(args);
        return authorize(args);
      },
      chat: {
        createModel: (profile) => {
          used.push(profile.model);
          return mock;
        },
      },
    });
    const ok = await chat(hono, { ...CHAT, grant: { grantId: 'g1', secret: 'secret' } });
    const events = aiEvents(await lines(ok));
    expect(used).toEqual(['grant-model']);
    expect(seen[0]?.agentGrant).toEqual(handle.overrides);
    expect(seen[0]?.principal.agentGrantId).toBe('g1');
    expect(events.map((e) => e.type)).toContain('approval_required');

    const refused = await chat(hono, { ...CHAT, grant: { grantId: 'g2', secret: 'secret' } });
    expect(refused.status).toBe(403);
    expect(await refused.json()).toMatchObject({ code: AI_GRANT_UNAVAILABLE });
  });
});

describe('POST /v1/ai/test', () => {
  it('runs the tool-calling smoke of the resolved profile and answers its verdict', async () => {
    const mock = new MockLanguageModelV4({ doStream: [textStep('no tool here')] });
    const hono = app(withAi('m'), { chat: { createModel: () => mock } });
    const answer = await post(hono, AI_ROUTES.test, {});
    expect(answer.status).toBe(200);
    expect(answer.body).toMatchObject({ ok: false, reason: 'no-tool-call' });
    const none = await post(app(fleetConfig()), AI_ROUTES.test, {});
    expect(none.status).toBe(404);
  });
});

describe('AiApprovalLedger', () => {
  const principal = {
    orgId: 'org-1',
    teamId: null,
    userId: 'user-owner',
    userEmail: 'owner@example.com',
    orgRole: 'owner' as const,
  };
  const event = {
    type: 'approval_required' as const,
    toolCallId: 'call-1',
    name: 'repo_delete',
    input: { ref: 'shop' },
  };
  const answer = (over: Partial<AiApprovalSubmit> = {}): AiApprovalSubmit => ({
    principal,
    conversationId: 'conv-1',
    toolCallId: 'call-1',
    approvalToken: 'tok',
    decision: 'approve',
    command: { pathKey: 'repo delete', params: {}, positionals: {} },
    stepUpMethod: null,
    destructive: true,
    grand: false,
    ...over,
  });

  it('redeems an expected approval once, for its own command and caller only', async () => {
    const ledger = new AiApprovalLedger();
    ledger.expect(principal, 'conv-1', event);
    const other = { command: { pathKey: 'repo up', params: {}, positionals: {} } };
    expect(await ledger.submit(answer(other))).toMatchObject({ ok: false, status: 409 });
    const stranger = { principal: { ...principal, userId: 'other' } };
    expect(await ledger.submit(answer(stranger))).toMatchObject({ ok: false, status: 404 });
    expect(await ledger.submit(answer())).toEqual({ ok: true });
    expect(await ledger.submit(answer())).toMatchObject({ ok: false, status: 404 });
  });

  it('forgets an approval after its window', async () => {
    let now = 0;
    const ledger = new AiApprovalLedger(() => now);
    ledger.expect(principal, 'conv-1', event);
    now = 16 * 60 * 1000;
    expect(await ledger.submit(answer())).toMatchObject({ ok: false, status: 404 });
  });
});
