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
import { AiEventSchema } from '@rediacc/shared/cli-contract/wire';
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

import { WK_ANTHROPIC_API_BASE } from '@rediacc/shared/config/well-known.generated';
import {
  AI_APPROVAL_COMMAND_MISMATCH,
  AI_APPROVAL_UNKNOWN,
  AiApprovalLedger,
  type AiApprovals,
} from '../../ai/approvals.js';
import { AiConversationStore } from '../../ai/autonomy.js';
import { DEFAULT_MAX_OUTPUT_TOKENS, MAX_TOOL_STEPS, STEP_LIMIT_REASON } from '../../ai/loop.js';
import { createProviderModel, type ProviderModelOptions } from '../../ai/provider.js';
import { AiTranscripts, createAiRecorder } from '../../ai/recorder.js';
import { outputService } from '../../core/output.js';
import {
  type AgentGrantHandle,
  AgentSessionRefused,
  AgentSessionUnavailable,
} from '../agent-grant-session.js';
import { AI_APPROVAL_STEPUP_REQUIRED } from '../ai-approval.js';
import { AI_GRANT_UNAVAILABLE } from '../ai-chat-tools.js';
import {
  AI_MODE_DISABLED,
  AI_PROFILE_UNRESOLVED,
  AI_ROUTES,
  type AiApprovalSubmit,
  type AiApprovalVerdict,
  type AiChatDeps,
  type AiChatRecording,
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
  tokenId: 'tok-owner',
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

/** The executor's own token may write audit records, so a dispatched mutation records its start. */
const EXECUTOR_SELF = { active: true, scopes: ['audit:write'] };

const fakeAccount = ((_url: string | URL, init?: RequestInit) => {
  const { token } = JSON.parse(String(init?.body ?? '{}')) as { token: string };
  const known: Record<string, object> = { [OWNER_TOKEN]: OWNER, rdt_executor: EXECUTOR_SELF };
  return Promise.resolve(Response.json(known[token] ?? { active: false }));
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
  /** A real ledger and store, for the token flow end to end; the recording fakes when absent. */
  approvals?: AiApprovals;
  modes?: AiConversationStore;
  executor?: ServeDeps['executor'];
  audit?: ServeDeps['audit'];
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
    executor: options.executor ?? {
      execute: () => Promise.reject(new Error('the approval route runs nothing')),
    },
    loadConfig: () => Promise.resolve(config),
    authorize: options.authorize ?? authorize,
    ...(options.agentGrants ? { agentGrants: options.agentGrants } : {}),
    ...(options.audit ? { audit: options.audit } : {}),
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
      modes: options.modes ?? {
        set: (_p, conversationId, mode) => modes.push({ conversationId, mode }),
        get: () => 'ask',
        allowExact: () => undefined,
        allowsExact: () => false,
      },
      approvals: options.approvals ?? {
        submit: (answer) => {
          submitted.push(answer);
          return Promise.resolve(verdict);
        },
        issue: (_p, _c, toolCallId) => `tok-${toolCallId}`,
        takeGrant: () => false,
        revokeGrant: () => undefined,
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
    baseURL: WK_ANTHROPIC_API_BASE,
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

  it('runs every tool call as the verified caller under the agent overrides, whatever kind or grant the body asserts', async () => {
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

  it("caps a turn's output at the profile's cap, and at the loop default when it names none", async () => {
    const capped = new MockLanguageModelV4({ doStream: [textStep('hi')] });
    const withCap: RdcConfig = {
      ...fleetConfig(),
      ai: { providers: { main: { ...profileOf('m'), maxOutputTokens: 1234 } }, default: 'main' },
    };
    await (await chat(app(withCap, { chat: { createModel: () => capped } }))).text();
    expect(capped.doStreamCalls[0]?.maxOutputTokens).toBe(1234);

    const plain = new MockLanguageModelV4({ doStream: [textStep('hi')] });
    await (await chat(app(withAi('m'), { chat: { createModel: () => plain } }))).text();
    expect(plain.doStreamCalls[0]?.maxOutputTokens).toBe(DEFAULT_MAX_OUTPUT_TOKENS);
    expect(DEFAULT_MAX_OUTPUT_TOKENS).toBe(8192);
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
        // A partial fake: the route calls acquire alone.
      } as unknown as ServeDeps['agentGrants'],
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

describe('a grant-bound chat that cannot open its grant', () => {
  const GRANT_CHAT = { ...CHAT, grant: { grantId: 'g1', secret: 'secret' } };

  it('answers 503 AI_GRANT_UNAVAILABLE when the grant session is unavailable, 400 when the executor serves none', async () => {
    const unavailable = app(withAi('m'), {
      agentGrants: {
        acquire: () => Promise.reject(new AgentSessionUnavailable('the account is unreachable')),
      } as unknown as ServeDeps['agentGrants'],
      chat: { createModel: () => new MockLanguageModelV4({ doStream: [textStep('hi')] }) },
    });
    const down = await chat(unavailable, GRANT_CHAT);
    expect(down.status).toBe(503);
    expect(await down.json()).toMatchObject({
      code: AI_GRANT_UNAVAILABLE,
      error: 'the account is unreachable',
    });
    const none = await chat(app(withAi('m')), GRANT_CHAT);
    expect(none.status).toBe(400);
    expect(await none.json()).toMatchObject({ code: AI_GRANT_UNAVAILABLE });
  });
});

describe('POST /v1/ai/chat on a Rediacc tier profile', () => {
  const TIER_CHAT = { ...CHAT, profile: 'rediacc:standard' };

  it('bills the Auto-mode judge to the caller and the conversation as well', async () => {
    const store = new AiConversationStore();
    store.set(
      {
        orgId: 'org-1',
        teamId: null,
        userId: 'user-owner',
        userEmail: 'owner@example.com',
        orgRole: 'owner',
      },
      CHAT.conversationId,
      'auto'
    );
    const built: { model: string; options: ProviderModelOptions | undefined }[] = [];
    const judgeAnswer = new MockLanguageModelV4({
      doGenerate: () =>
        Promise.resolve({
          content: [{ type: 'text', text: '{"verdict":"allow","reason":"asked for"}' }],
          finishReason: { unified: 'stop', raw: 'stop' },
          usage: USAGE,
          warnings: [],
        }),
    });
    const chatModel = new MockLanguageModelV4({
      doStream: [toolCallStep('repo_up', { ref: 'shop:trial' }), textStep('Done.')],
    });
    const hono = app(fleetConfig({ version: 1, defaults: { commands: { allow: ['*'] } } }), {
      modes: store,
      approvals: new AiApprovalLedger(),
      chat: {
        createModel: (profile, options) => {
          built.push({ model: profile.model, options });
          return built.length === 1 ? chatModel : judgeAnswer;
        },
      },
    });
    await (await chat(hono, TIER_CHAT)).text();
    const billed = { rediacc: { userId: 'user-owner', conversationId: 'conv-1' } };
    expect(built.map((b) => b.options)).toEqual([billed, billed]);
    expect(judgeAnswer.doGenerateCalls).toHaveLength(1);
  });

  it('builds the model with the caller and the conversation as the billing ids', async () => {
    const seen: (ProviderModelOptions | undefined)[] = [];
    const mock = new MockLanguageModelV4({ doStream: [textStep('hi')] });
    const chatDeps: AiChatDeps = {
      createModel: (_profile, options) => {
        seen.push(options);
        return mock;
      },
    };
    const response = await chat(app(fleetConfig(), { chat: chatDeps }), TIER_CHAT);
    await response.text();
    expect(response.status).toBe(200);
    expect(seen).toEqual([{ rediacc: { userId: 'user-owner', conversationId: 'conv-1' } }]);
  });

  it('surfaces a ledger refusal as an error event with its AI_CREDITS code', async () => {
    const gateway: typeof globalThis.fetch = () =>
      Promise.resolve(
        Response.json(
          { error: { code: 'INSUFFICIENT_CREDITS' }, code: 'INSUFFICIENT_CREDITS' },
          { status: 402 }
        )
      );
    const chatDeps: AiChatDeps = {
      createModel: (profile, options) =>
        createProviderModel(profile, { ...options, fetch: gateway }),
    };
    const response = await chat(app(fleetConfig(), { chat: chatDeps }), TIER_CHAT);
    const events = aiEvents(await lines(response));
    expect(events.find((e) => e.type === 'error')).toMatchObject({
      type: 'error',
      code: 'AI_CREDITS_INSUFFICIENT_CREDITS',
    });
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

describe('the approval token, end to end', () => {
  const OWNER_PRINCIPAL = {
    orgId: 'org-1',
    teamId: null,
    userId: 'user-owner',
    userEmail: 'owner@example.com',
    orgRole: 'owner' as const,
  };
  /** Every command is allowed, so only the autonomy gate holds a call. */
  const OPEN: PolicyDocument = { version: 1, defaults: { commands: { allow: ['*'] } } };
  const UP_TRIAL = { pathKey: 'repo up', params: {}, positionals: { ref: 'shop:trial' } };

  interface Flow {
    hono: Hono;
    store: AiConversationStore;
    audited: { commandPath: string; outcome?: string; success: boolean }[];
    /** The request id each audit record carried, by command path. */
    requestIds: Map<string, (string | undefined)[]>;
    /** Dispatches the tool calls reached: one `started` audit record per mutating run. */
    started: () => number;
  }

  function flow(
    policy: PolicyDocument = OPEN,
    extra: {
      judge?: AiChatDeps['judge'];
      failApprovalAudit?: boolean;
      /** Reject the audit record of every command path this answers true for. */
      failAudit?: (commandPath: string) => boolean;
      chat?: Pick<AiChatDeps, 'recording' | 'cancelJob'>;
      executor?: ServeDeps['executor'];
    } = {}
  ): Flow {
    const store = new AiConversationStore();
    const audited: Flow['audited'] = [];
    const requestIds: Flow['requestIds'] = new Map();
    const hono = app(
      { ...fleetConfig(policy), ai: aiOf('m') },
      {
        approvals: new AiApprovalLedger(),
        modes: store,
        ...(extra.executor ? { executor: extra.executor } : {}),
        audit: (event) => {
          if (
            (extra.failApprovalAudit && event.commandPath.startsWith('ai approval')) ||
            extra.failAudit?.(event.commandPath)
          ) {
            return Promise.reject(new Error('audit sink down'));
          }
          requestIds.set(event.commandPath, [
            ...(requestIds.get(event.commandPath) ?? []),
            event.requestId,
          ]);
          audited.push({
            commandPath: event.commandPath,
            success: event.success,
            ...(event.outcome ? { outcome: event.outcome } : {}),
          });
          return Promise.resolve();
        },
        chat: {
          createModel: () =>
            new MockLanguageModelV4({
              doStream: [toolCallStep(toolOf.name, toolOf.input), textStep('Done.')],
            }),
          ...(extra.judge ? { judge: extra.judge } : {}),
          ...extra.chat,
        },
      }
    );
    const started = () => audited.filter((a) => a.outcome === 'started').length;
    return { hono, store, audited, requestIds, started };
  }

  /** The tool call the next chat's model makes. */
  let toolOf: { name: string; input: Record<string, unknown> };

  beforeEach(() => {
    toolOf = { name: 'repo_up', input: { ref: 'shop:trial' } };
  });

  async function turnEvents(hono: Hono) {
    return aiEvents(await lines(await chat(hono)));
  }

  async function pendingApproval(hono: Hono) {
    const held = (await turnEvents(hono)).find((e) => e.type === 'approval_required');
    expect(held).toBeDefined();
    return held as {
      approvalToken: string;
      toolCallId: string;
      command: typeof UP_TRIAL;
      risk: string;
      reason?: string;
    };
  }

  const answer = (
    held: { approvalToken: string; toolCallId: string; command: object },
    over: Record<string, unknown> = {}
  ) => ({
    conversationId: CHAT.conversationId,
    toolCallId: held.toolCallId,
    approvalToken: held.approvalToken,
    decision: 'approve',
    command: held.command,
    stepUpMethod: null,
    ...over,
  });

  it('issues a single-use token bound to the exact command, and the event parses on the wire', async () => {
    const { hono, started } = flow();
    const raw = (await turnEvents(hono)).find((e) => e.type === 'approval_required');
    const wire = AiEventSchema.parse(raw);
    expect(wire).toMatchObject({ type: 'approval_required', command: UP_TRIAL, risk: 'caution' });
    const held = await pendingApproval(hono);
    expect(held.approvalToken).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(held.command).toEqual(UP_TRIAL);
    expect(held.risk).toBe('caution');
    expect(held.reason).toContain('Ask mode');
    expect(started()).toBe(0);
    const again = await pendingApproval(hono);
    expect(again.approvalToken).not.toBe(held.approvalToken);
  });

  it('runs an approved command exactly once, and records the approval', async () => {
    const { hono, audited, started } = flow();
    const held = await pendingApproval(hono);
    const approved = await post(hono, AI_ROUTES.approval, answer(held));
    expect(approved.status).toBe(200);
    expect(audited).toContainEqual({ commandPath: 'ai approval repo up', success: true });

    const ran = await turnEvents(hono);
    expect(ran.map((e) => e.type)).not.toContain('approval_required');
    expect(started()).toBe(1);

    const next = await turnEvents(hono);
    expect(next.map((e) => e.type)).toContain('approval_required');
    expect(started()).toBe(1);
  });

  it('refuses a forged token, and runs nothing', async () => {
    const { hono, started } = flow();
    const held = await pendingApproval(hono);
    const forged = { ...held, approvalToken: 'A'.repeat(43) };
    const refused = await post(hono, AI_ROUTES.approval, answer(forged));
    expect(refused).toMatchObject({ status: 404, body: { code: AI_APPROVAL_UNKNOWN } });
    await turnEvents(hono);
    expect(started()).toBe(0);
  });

  it('refuses a reused token', async () => {
    const { hono } = flow();
    const held = await pendingApproval(hono);
    expect((await post(hono, AI_ROUTES.approval, answer(held))).status).toBe(200);
    const replay = await post(hono, AI_ROUTES.approval, answer(held));
    expect(replay).toMatchObject({ status: 404, body: { code: AI_APPROVAL_UNKNOWN } });
  });

  it('refuses a token presented for another command, and keeps it for its own', async () => {
    const { hono, started } = flow();
    const held = await pendingApproval(hono);
    const other = answer(held, {
      command: { pathKey: 'repo up', params: {}, positionals: { ref: 'shop' } },
      stepUpMethod: 'passkey',
    });
    const refused = await post(hono, AI_ROUTES.approval, other);
    expect(refused).toMatchObject({ status: 409, body: { code: AI_APPROVAL_COMMAND_MISMATCH } });
    await turnEvents(hono);
    expect(started()).toBe(0);
    expect((await post(hono, AI_ROUTES.approval, answer(held))).status).toBe(200);
  });

  it('refuses a token presented for another conversation or tool call', async () => {
    const { hono } = flow();
    const held = await pendingApproval(hono);
    const elsewhere = await post(
      hono,
      AI_ROUTES.approval,
      answer(held, { conversationId: 'conv-2' })
    );
    expect(elsewhere).toMatchObject({ status: 404, body: { code: AI_APPROVAL_UNKNOWN } });
    const otherCall = await post(hono, AI_ROUTES.approval, answer(held, { toolCallId: 'call-9' }));
    expect(otherCall).toMatchObject({ status: 404, body: { code: AI_APPROVAL_UNKNOWN } });
  });

  it('leaves no grant behind a rejection', async () => {
    const { hono, audited, started } = flow();
    const held = await pendingApproval(hono);
    const rejected = await post(hono, AI_ROUTES.approval, answer(held, { decision: 'reject' }));
    expect(rejected.status).toBe(200);
    expect(audited).toContainEqual({ commandPath: 'ai approval repo up', success: false });
    expect((await turnEvents(hono)).map((e) => e.type)).toContain('approval_required');
    expect(started()).toBe(0);
  });

  it('withdraws an approval whose audit record cannot be delivered', async () => {
    const { hono, started } = flow(OPEN, { failApprovalAudit: true });
    const held = await pendingApproval(hono);
    expect((await post(hono, AI_ROUTES.approval, answer(held))).status).toBe(500);
    expect((await turnEvents(hono)).map((e) => e.type)).toContain('approval_required');
    expect(started()).toBe(0);
  });

  it('remembers an exact allow rule only when asked, for a caution command', async () => {
    const { hono, started } = flow();
    const held = await pendingApproval(hono);
    expect((await post(hono, AI_ROUTES.approval, answer(held, { remember: true }))).status).toBe(
      200
    );
    await turnEvents(hono);
    await turnEvents(hono);
    expect(started()).toBe(2);
    toolOf = { name: 'repo_up', input: { ref: 'shop:trial', no_start: true } };
    expect((await turnEvents(hono)).map((e) => e.type)).toContain('approval_required');
  });

  it('runs a caution command in Skip mode, and still holds a destructive one', async () => {
    const { hono, store, started } = flow();
    store.set(OWNER_PRINCIPAL, CHAT.conversationId, 'skip');
    await turnEvents(hono);
    expect(started()).toBe(1);
    toolOf = { name: 'repo_down', input: { ref: 'shop:trial' } };
    const held = await pendingApproval(hono);
    expect(held.risk).toBe('destructive');
    expect(started()).toBe(1);
  });

  it('reads a mode the policy disabled as Ask', async () => {
    const { hono, store, started } = flow({
      ...OPEN,
      defaults: { ...OPEN.defaults, aiModesDisabled: ['skip'] },
    });
    store.set(OWNER_PRINCIPAL, CHAT.conversationId, 'skip');
    const held = await pendingApproval(hono);
    expect(held.reason).toContain('Ask mode');
    expect(started()).toBe(0);
  });

  it('asks the judge in Auto mode, and holds what it blocks', async () => {
    let verdict: 'allow' | 'block' = 'allow';
    const seen: unknown[] = [];
    const { hono, store, started } = flow(OPEN, {
      judge: (_profile, input) => {
        seen.push(input);
        return Promise.resolve({ verdict, reason: 'because' });
      },
    });
    store.set(OWNER_PRINCIPAL, CHAT.conversationId, 'auto');
    await turnEvents(hono);
    expect(started()).toBe(1);
    expect(seen[0]).toMatchObject({
      command: { pathKey: 'repo up', argv: ['repo', 'up', 'shop:trial'] },
    });
    verdict = 'block';
    const held = await pendingApproval(hono);
    expect(held.reason).toContain('judge');
    expect(started()).toBe(1);
  });

  it('records each judge verdict, the fallback to Ask, and the mode changes', async () => {
    let verdict: 'allow' | 'block' = 'allow';
    const { hono, store, audited, requestIds } = flow(OPEN, {
      judge: () => Promise.resolve({ verdict, reason: 'because' }),
    });
    store.set(OWNER_PRINCIPAL, CHAT.conversationId, 'auto');
    await turnEvents(hono);
    verdict = 'block';
    for (let i = 0; i < 3; i += 1) await turnEvents(hono);
    const paths = audited.map((a) => `${a.commandPath}:${a.success}`);
    expect(paths.filter((p) => p === 'ai judge repo up:true')).toHaveLength(1);
    expect(paths.filter((p) => p === 'ai judge repo up:false')).toHaveLength(3);
    expect(paths.filter((p) => p === 'ai mode ask:true')).toHaveLength(1);
    // Every judge record and the fallback carry the tool call's request id, which joins them to the run.
    for (const path of ['ai judge repo up', 'ai mode ask']) {
      const ids = requestIds.get(path) ?? [];
      expect(ids.length).toBeGreaterThan(0);
      expect(ids.every((id) => id === `${CHAT.conversationId}:call-1`)).toBe(true);
    }
    await post(hono, AI_ROUTES.mode, { conversationId: CHAT.conversationId, mode: 'skip' });
    await post(hono, AI_ROUTES.mode, { conversationId: CHAT.conversationId, mode: 'skip' });
    expect(audited.filter((a) => a.commandPath === 'ai mode skip')).toHaveLength(1);
  });

  it('puts the mode back when its record cannot be delivered, and answers the failure', async () => {
    const { hono, store, audited } = flow(OPEN, { failAudit: (p) => p.startsWith('ai mode') });
    const refused = await post(hono, AI_ROUTES.mode, {
      conversationId: CHAT.conversationId,
      mode: 'skip',
    });
    expect(refused.status).toBe(500);
    expect(store.get(OWNER_PRINCIPAL, CHAT.conversationId)).toBe('ask');
    expect(audited).toEqual([]);
  });

  it('fails a call whose judge record cannot be delivered, and still ships the fallback to Ask', async () => {
    const sink: { failJudge: boolean } = { failJudge: false };
    const { hono, store, audited, started } = flow(OPEN, {
      judge: () => Promise.resolve({ verdict: 'block', reason: 'because' }),
      failAudit: (p) => sink.failJudge && p.startsWith('ai judge'),
    });
    store.set(OWNER_PRINCIPAL, CHAT.conversationId, 'auto');
    await turnEvents(hono);
    await turnEvents(hono);
    sink.failJudge = true;
    const events = await turnEvents(hono);
    expect(events.find((e) => e.type === 'tool_result')).toMatchObject({ ok: false });
    expect(started()).toBe(0);
    expect(store.get(OWNER_PRINCIPAL, CHAT.conversationId)).toBe('ask');
    expect(audited.filter((a) => a.commandPath === 'ai mode ask')).toHaveLength(1);
  });

  it('hands a started job back as an ok result once the answer window passes', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    try {
      const { hono, store } = flow(OPEN, {
        executor: {
          execute: (options) =>
            new Promise(() => {
              options.onJobStarted?.('job-7', options.machineName);
            }),
        },
      });
      store.set(OWNER_PRINCIPAL, CHAT.conversationId, 'skip');
      const turn = chat(hono).then((response) => lines(response));
      for (let i = 0; i < 40; i += 1) await vi.advanceTimersByTimeAsync(10_000);
      const events = aiEvents(await turn);
      expect(events.find((e) => e.type === 'tool_result')).toMatchObject({
        ok: true,
        output: { status: 'ok', exitCode: 0 },
      });
      expect(JSON.stringify(events)).toContain('job-7');
    } finally {
      vi.useRealTimers();
    }
  });

  it('warns when the cancel of a job cannot be recorded, and does not cancel it', async () => {
    const warn = vi.spyOn(outputService, 'warn').mockImplementation(() => undefined);
    const cancelled: string[] = [];
    let announce: () => void = () => undefined;
    const announced = new Promise<void>((resolve) => {
      announce = resolve;
    });
    try {
      const { hono, store } = flow(OPEN, {
        failAudit: (p) => p === 'job cancel',
        executor: {
          execute: (options) =>
            new Promise(() => {
              options.onJobStarted?.('job-1', options.machineName);
              announce();
            }),
        },
        chat: {
          cancelJob: (_machine, jobId) => {
            cancelled.push(jobId);
            return Promise.resolve();
          },
        },
      });
      store.set(OWNER_PRINCIPAL, CHAT.conversationId, 'skip');
      const abort = new AbortController();
      await chat(hono, CHAT, { signal: abort.signal });
      await announced;
      abort.abort();
      await vi.waitFor(() =>
        expect(warn).toHaveBeenCalledWith(expect.stringContaining('job job-1 on m1'))
      );
      expect(cancelled).toEqual([]);
    } finally {
      warn.mockRestore();
    }
  });

  it('records the refusal of a destructive approval that names no step-up', async () => {
    toolOf = { name: 'repo_delete', input: { ref: 'shop:trial' } };
    const { hono, audited } = flow();
    const held = await pendingApproval(hono);
    const refused = await post(hono, AI_ROUTES.approval, answer(held));
    expect(refused.status).toBe(403);
    expect(audited).toContainEqual({ commandPath: 'ai refusal repo delete', success: false });
  });

  it('records the refusal of a mode the policy disabled', async () => {
    const { hono, audited } = flow({
      version: 1,
      defaults: { commands: { allow: ['*'] }, aiModesDisabled: ['auto'] },
    });
    const refused = await post(hono, AI_ROUTES.mode, {
      conversationId: CHAT.conversationId,
      mode: 'auto',
    });
    expect(refused.status).toBe(403);
    expect(audited).toEqual([{ commandPath: 'ai refusal', success: false }]);
  });

  /** The account's conversation store as `POST /console/ai/messages` keeps it: a row per conversation, replays no-ops. */
  function accountStore() {
    const rows = new Map<string, Record<string, unknown>[]>();
    const fetchImpl = ((_url: string | URL, init?: RequestInit) => {
      const write = JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>;
      const id = String(write.conversationId);
      const messages = rows.get(id) ?? [];
      if (messages.some((m) => m.messageId === write.messageId)) {
        return Promise.resolve(Response.json({ ok: true, created: false }));
      }
      if (write.parentId && !messages.some((m) => m.messageId === write.parentId)) {
        return Promise.resolve(Response.json({ code: 'AI_PARENT_MISSING' }, { status: 409 }));
      }
      rows.set(id, [...messages, write]);
      return Promise.resolve(Response.json({ ok: true, created: true }));
    }) as typeof fetch;
    const recording: AiChatRecording = {
      transcripts: new AiTranscripts(
        createAiRecorder({
          accountUrl: 'https://account.test',
          executorToken: 'rdt_executor',
          fetchImpl,
        })
      ),
      keyOf: () => ({ cekGeneration: 1, cek: () => Promise.resolve(new Uint8Array(32).fill(7)) }),
    };
    return { rows, recording };
  }

  /**
   * The page's approval as the account route answers it (private/account/src/routes/console-ai.ts
   * `POST /conversations/:id/approvals`): a conversation the store holds no row for is a 404, and
   * one it holds is forwarded with the step-up the account judged and the `remember` flag.
   */
  function pageApproval(
    hono: Hono,
    rows: Map<string, unknown[]>,
    held: { approvalToken: string; toolCallId: string; command: object },
    remember?: boolean
  ) {
    if (!rows.has(CHAT.conversationId)) {
      return Promise.resolve({ status: 404, body: { error: 'Conversation not found' } });
    }
    return post(hono, AI_ROUTES.approval, answer(held, remember === undefined ? {} : { remember }));
  }

  it('approves a held call from the page: the turn recorded the conversation the account looks up', async () => {
    const { rows, recording } = accountStore();
    const { hono, started } = flow(OPEN, { chat: { recording } });
    const held = await pendingApproval(hono);
    const stored = rows.get(CHAT.conversationId) ?? [];
    expect(stored).toHaveLength(1);
    expect(stored[0]).toMatchObject({
      conversationId: CHAT.conversationId,
      parentId: null,
      seq: 0,
      onBehalfOfTokenId: 'tok-owner',
      cekGeneration: 1,
    });
    expect(typeof stored[0]?.titleSealed).toBe('string');

    expect((await pageApproval(hono, rows, held, true)).status).toBe(200);
    const ran = await turnEvents(hono);
    expect(ran.map((e) => e.type)).not.toContain('approval_required');
    expect(started()).toBe(1);
    // The reply of the turn that ran is recorded under the user's message; the replayed message is not posted again.
    expect((rows.get(CHAT.conversationId) ?? []).map((m) => [m.seq, m.parentId])).toEqual([
      [0, null],
      [1, stored[0]?.messageId],
    ]);
  });

  it('cancels the machine job of a running tool call when the client aborts', async () => {
    const cancelled: [string, string][] = [];
    let announce: () => void = () => undefined;
    const announced = new Promise<void>((resolve) => {
      announce = resolve;
    });
    const { hono, store, audited } = flow(OPEN, {
      executor: {
        execute: (options) =>
          new Promise(() => {
            options.onJobStarted?.('job-1', options.machineName);
            announce();
          }),
      },
      chat: {
        cancelJob: (machine, jobId) => {
          cancelled.push([machine, jobId]);
          return Promise.resolve();
        },
      },
    });
    store.set(OWNER_PRINCIPAL, CHAT.conversationId, 'skip');
    const abort = new AbortController();
    const response = await chat(hono, CHAT, { signal: abort.signal });
    expect(response.status).toBe(200);
    await announced;
    expect(cancelled).toEqual([]);
    abort.abort();
    await vi.waitFor(() => expect(cancelled).toEqual([['m1', 'job-1']]));
    await vi.waitFor(() =>
      expect(audited.filter((a) => a.commandPath === 'job cancel')).toEqual([
        { commandPath: 'job cancel', success: true, outcome: 'started' },
        { commandPath: 'job cancel', success: true },
      ])
    );
  });
});
