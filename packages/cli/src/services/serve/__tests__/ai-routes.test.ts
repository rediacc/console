/**
 * The executor's AI mode and approval routes (AI5 of agent/plans/PLAN-console-ai-assistant.md).
 *
 * The mode route refuses a mode the policy disabled (D6). The approval route resolves the target
 * itself and refuses an approval of a destructive command or a grand-repo target that arrives
 * without the step-up method the account must have checked (C12, C13), whatever the browser said
 * about `grand`; the single-use token goes to the loop's approval ledger, whose refusal passes
 * through. The real contract, policy code and repo resolver run; the account server is faked.
 */

import type { RdcConfig } from '@rediacc/shared/config-schema';
import type { PolicyDocument } from '@rediacc/shared/policy';
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

import {
  AI_APPROVAL_STEPUP_REQUIRED,
  AI_MODE_DISABLED,
  AI_ROUTES,
  type AiApprovalSubmit,
  type AiApprovalVerdict,
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

function app(config: RdcConfig): Hono {
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
    authorize,
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
      },
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
      ...approval('machine list', 'x'),
      command: { pathKey: 'machine list', params: {}, positionals: {} },
    });
    expect(config.status).toBe(400);
    expect((await post(hono, AI_ROUTES.approval, approval('no such', 'x'))).status).toBe(400);
    expect(submitted).toEqual([]);
  });
});
