/**
 * Agent-grant sessions (agent/plans/PLAN-rmcp-agent-grants.md box AG-X, Design 4): one session per grant, rebuilt from the
 * secret after a sleep, with the secret never held. The account server is a fake with real ciphertext (agent-grant-harness.ts).
 */

import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { boundEffectivePolicy } from '../../config/policy-record.js';
import {
  AgentGrantSessions,
  AgentSessionRefused,
  AgentSessionUnavailable,
} from '../agent-grant-session.js';
import { AuthError } from '../auth.js';
import { routeAgentPrincipals } from '../container-config.js';
import { serveCrypto } from '../crypto.js';
import type { ServeDeps } from '../deps.js';
import { createServeApp } from '../server.js';
import { SessionError, SessionStore } from '../sessions.js';
import {
  configOf,
  EXECUTOR_TOKEN,
  type FakeAccount,
  fakeAccount,
  makeGrant,
  OPEN_POLICY,
  ORG_CONFIG_ID,
  ORG_ID,
} from './agent-grant-harness.js';

afterEach(() => {
  vi.restoreAllMocks();
});

async function world() {
  // Two grants of ONE user, each on its own team's config.
  const a = await makeGrant({
    grantId: 'g_team_a',
    teamId: 'team-a',
    configId: 'cfg-a',
    machine: 'machine-a',
  });
  const b = await makeGrant({
    grantId: 'g_team_b',
    teamId: 'team-b',
    configId: 'cfg-b',
    machine: 'machine-b',
  });
  const account = fakeAccount([a, b]);
  const sessions = new AgentGrantSessions({
    accountUrl: 'https://account.test',
    executorToken: EXECUTOR_TOKEN,
    orgId: ORG_ID,
    fetchImpl: account.fetch,
  });
  return { a, b, account, sessions };
}

const machinesOf = (config: { resources?: { machines?: Record<string, unknown> } }) =>
  Object.keys(config.resources?.machines ?? {});

const principalOf = (agentGrantId: string) => ({
  orgId: ORG_ID,
  teamId: null,
  userId: 'u',
  userEmail: 'e',
  orgRole: 'member' as const,
  agentGrantId,
});

/**
 * Holds every agent-session answer until `release`, and counts the calls that reached the session lookup, so a race
 * test releases the open only once the second call is truly waiting on (or joining) it.
 */
function holdOpens(account: FakeAccount, sessions: AgentGrantSessions) {
  let release = () => {};
  account.holdOpens = new Promise<void>((resolve) => {
    release = resolve;
  });
  let reached = 0;
  const target = sessions as unknown as {
    recordFor: (...args: unknown[]) => Promise<unknown>;
  };
  const original = target.recordFor.bind(sessions);
  vi.spyOn(target, 'recordFor').mockImplementation((...args: unknown[]) => {
    reached += 1;
    return original(...args);
  });
  const reachedRecord = (count: number) => vi.waitFor(() => expect(reached).toBe(count));
  return { release, reachedRecord };
}

describe('agent grant sessions', () => {
  it('holds two sessions with two configs for two grants of one user (the cross-team regression)', async () => {
    const { a, b, sessions } = await world();

    const first = await sessions.acquire(a.grantId, a.secret);
    const second = await sessions.acquire(b.grantId, b.secret);

    expect(sessions.size).toBe(2);
    expect(machinesOf(first.config)).toEqual(['machine-a']);
    expect(machinesOf(second.config)).toEqual(['machine-b']);
    expect(first.config.credentials?.ssh?.privateKey).toBe('KEY-cfg-a');
    expect(second.config.credentials?.ssh?.privateKey).toBe('KEY-cfg-b');
    // The loader's routing hands each principal its OWN grant's config.
    expect(machinesOf(sessions.currentConfig(first.principal))).toEqual(['machine-a']);
    expect(machinesOf(sessions.currentConfig(second.principal))).toEqual(['machine-b']);
    expect(first.principal.teamId).toBe('team-a');
    expect(second.principal.teamId).toBe('team-b');
    expect(first.principal.agentGrantId).toBe('g_team_a');
    expect(first.overrides).toEqual({ allowGrandRepos: false, allowClusterOps: false });
  });

  it('runs as its person: the role, email and team slug the account answered, and the policy of its records', async () => {
    const team = { version: 1 as const, defaults: { commands: { allow: ['repo *'] } } };
    const grant = await makeGrant({
      grantId: 'g_person',
      teamId: 'team-a',
      configId: 'cfg-a',
      machine: 'machine-a',
      orgRole: 'member',
      userEmail: 'ada@example.test',
      policies: { team },
    });
    const account = fakeAccount([grant]);
    const sessions = new AgentGrantSessions({
      accountUrl: 'https://account.test',
      executorToken: EXECUTOR_TOKEN,
      orgId: ORG_ID,
      fetchImpl: account.fetch,
    });

    const handle = await sessions.acquire(grant.grantId, grant.secret);
    expect(handle.principal).toMatchObject({
      orgRole: 'member',
      userEmail: 'ada@example.test',
      teamId: 'team-a',
      teamSlug: 'slug-team-a',
      agentGrantId: 'g_person',
    });
    // Two wraps for a team grant; the org record was read from the org-level config the listing names.
    expect(grant.policyKeys.map((entry) => entry.policyConfigId)).toEqual(['cfg-a', ORG_CONFIG_ID]);
    expect(account.count(`GET /configs/${ORG_CONFIG_ID}/policy`)).toBe(1);
    const effective = boundEffectivePolicy(handle.config);
    expect(effective?.org).toEqual(OPEN_POLICY);
    expect(effective?.team).toEqual(team);
  });

  it('opens a grant on the org-level config with its one policy key', async () => {
    const org = { version: 1 as const, defaults: { commands: { allow: ['machine *'] } } };
    const grant = await makeGrant({
      grantId: 'g_org',
      configId: 'cfg-org-own',
      machine: 'machine-o',
      policies: { org },
    });
    const account = fakeAccount([grant]);
    const sessions = new AgentGrantSessions({
      accountUrl: 'https://account.test',
      executorToken: EXECUTOR_TOKEN,
      orgId: ORG_ID,
      fetchImpl: account.fetch,
    });

    expect(grant.policyKeys).toHaveLength(1);
    const handle = await sessions.acquire(grant.grantId, grant.secret);
    expect(boundEffectivePolicy(handle.config)?.org).toEqual(org);
    expect(account.count('GET /configs/cfg-org-own/policy')).toBe(0);
  });

  it('refuses a grant with no policy key, and does not hold it', async () => {
    const grant = await makeGrant({
      grantId: 'g_nowrap',
      teamId: 'team-a',
      configId: 'cfg-a',
      machine: 'machine-a',
      wraps: false,
    });
    const account = fakeAccount([grant]);
    const sessions = new AgentGrantSessions({
      accountUrl: 'https://account.test',
      executorToken: EXECUTOR_TOKEN,
      orgId: ORG_ID,
      fetchImpl: account.fetch,
    });

    await expect(sessions.acquire(grant.grantId, grant.secret)).rejects.toBeInstanceOf(
      AgentSessionRefused
    );
    expect(sessions.has(grant.grantId)).toBe(false);
    expect(account.count('GET /configs')).toBe(0);
  });

  it('refuses a team grant missing the org-level key while the org policy record exists', async () => {
    const grant = await makeGrant({
      grantId: 'g_noorg',
      teamId: 'team-a',
      configId: 'cfg-a',
      machine: 'machine-a',
    });
    grant.policyKeys = grant.policyKeys.filter((entry) => entry.policyConfigId === 'cfg-a');
    const account = fakeAccount([grant]);
    const sessions = new AgentGrantSessions({
      accountUrl: 'https://account.test',
      executorToken: EXECUTOR_TOKEN,
      orgId: ORG_ID,
      fetchImpl: account.fetch,
    });

    await expect(sessions.acquire(grant.grantId, grant.secret)).rejects.toThrow(
      /no policy key for config cfg-org/
    );
    expect(sessions.has(grant.grantId)).toBe(false);
  });

  it('rebuilds from S with one agent-session call after a simulated sleep, and not before', async () => {
    const { a, account, sessions } = await world();

    await sessions.acquire(a.grantId, a.secret);
    await sessions.acquire(a.grantId, a.secret);
    // Warm: one open for two calls.
    expect(account.count('POST /configs/agent-session')).toBe(1);

    // The container slept: the store is gone, the next call rebuilds from the secret it carries.
    sessions.drop(a.grantId);
    const rebuilt = await sessions.acquire(a.grantId, a.secret);
    expect(account.count('POST /configs/agent-session')).toBe(2);
    expect(machinesOf(rebuilt.config)).toEqual(['machine-a']);
    // The tag the account got is derived from S, never S itself.
    for (const body of account.openBodies) expect(JSON.stringify(body)).not.toContain(a.secret);
  });

  it('never lets S reach the session store, a log line or an error message', async () => {
    const { a, b, account, sessions } = await world();
    const logged: string[] = [];
    for (const method of ['log', 'info', 'warn', 'error', 'debug'] as const) {
      vi.spyOn(console, method).mockImplementation((...args: unknown[]) => {
        logged.push(args.map(String).join(' '));
      });
    }
    const written: string[] = [];
    vi.spyOn(process.stderr, 'write').mockImplementation((chunk: unknown) => {
      written.push(String(chunk));
      return true;
    });

    await sessions.acquire(a.grantId, a.secret);
    const wrong = await sessions.acquire(a.grantId, b.secret).catch((error: unknown) => error);
    account.refused.add(b.grantId);
    const refused = await sessions.acquire(b.grantId, b.secret).catch((error: unknown) => error);

    // What the store holds, serialized (the non-extractable keys are opaque), then searched for either secret.
    const store = (sessions as unknown as { sessions: Map<string, unknown> }).sessions;
    const held = JSON.stringify([...store.values()]);
    const hex = (bytes: Uint8Array) => Buffer.from(bytes).toString('hex');
    for (const grant of [a, b]) {
      for (const needle of [grant.secret, hex(grant.secretBytes)]) {
        expect(held).not.toContain(needle);
        expect(logged.join('\n')).not.toContain(needle);
        expect(written.join('\n')).not.toContain(needle);
        expect(String((wrong as Error).message)).not.toContain(needle);
        expect(String((refused as Error).message)).not.toContain(needle);
      }
    }
  });

  it('drops the session when the account refuses the grant', async () => {
    const { a, account, sessions } = await world();
    await sessions.acquire(a.grantId, a.secret);
    expect(sessions.has(a.grantId)).toBe(true);

    // The chain's token lapses and the grant was revoked meanwhile: the fresh open is refused.
    account.expireNextToken = true;
    account.refused.add(a.grantId);
    await expect(sessions.acquire(a.grantId, a.secret)).rejects.toBeInstanceOf(AgentSessionRefused);

    expect(sessions.has(a.grantId)).toBe(false);
    expect(() => sessions.currentConfig(principalOf(a.grantId))).toThrow(SessionError);
  });

  it('does not hold a grant the account refuses at the first open', async () => {
    const { b, account, sessions } = await world();
    account.refused.add(b.grantId);
    await expect(sessions.acquire(b.grantId, b.secret)).rejects.toBeInstanceOf(AgentSessionRefused);
    expect(sessions.size).toBe(0);
  });

  it('refuses a secret that is not the grant, without dropping the grant', async () => {
    const { a, b, sessions } = await world();
    await sessions.acquire(a.grantId, a.secret);
    await expect(sessions.acquire(a.grantId, b.secret)).rejects.toBeInstanceOf(AgentSessionRefused);
    await expect(sessions.acquire(a.grantId, 'not-base64url!')).rejects.toBeInstanceOf(
      AgentSessionRefused
    );
    expect(sessions.has(a.grantId)).toBe(true);
  });

  it('refuses a wrong secret that arrives while the right one is opening the grant', async () => {
    const { a, b, account, sessions } = await world();
    const { release, reachedRecord } = holdOpens(account, sessions);

    const right = sessions.acquire(a.grantId, a.secret);
    await vi.waitFor(() => expect(account.count('POST /configs/agent-session')).toBe(1));
    // The open is in flight; a call carrying another grant's secret for this grant must not join it.
    const wrong = sessions.acquire(a.grantId, b.secret).catch((error: unknown) => error);
    await reachedRecord(2);
    release();

    expect(machinesOf((await right).config)).toEqual(['machine-a']);
    expect(await wrong).toBeInstanceOf(AgentSessionRefused);
    expect(sessions.has(a.grantId)).toBe(true);
    expect(account.count('POST /configs/agent-session')).toBe(1);
  });

  it('opens the grant for the right secret after a wrong one in flight is refused', async () => {
    const { a, b, account, sessions } = await world();
    const { release, reachedRecord } = holdOpens(account, sessions);

    const wrong = sessions.acquire(a.grantId, b.secret).catch((error: unknown) => error);
    await vi.waitFor(() => expect(account.count('POST /configs/agent-session')).toBe(1));
    // The right secret does not inherit the wrong open's refusal: it waits, then opens on its own.
    const right = sessions.acquire(a.grantId, a.secret);
    await reachedRecord(2);
    release();

    expect(await wrong).toBeInstanceOf(AgentSessionRefused);
    expect(machinesOf((await right).config)).toEqual(['machine-a']);
    expect(sessions.has(a.grantId)).toBe(true);
    expect(account.count('POST /configs/agent-session')).toBe(2);
  });

  it('keys the cached config by its version: same version no pull, a new version one pull', async () => {
    const { a, account, sessions } = await world();
    await sessions.acquire(a.grantId, a.secret);
    await sessions.acquire(a.grantId, a.secret);
    expect(account.count('GET /configs/cfg-a')).toBe(1);

    await account.bump(a.grantId, configOf('cfg-a', 'machine-a2'));
    const next = await sessions.acquire(a.grantId, a.secret);

    expect(account.count('GET /configs/cfg-a')).toBe(2);
    expect(machinesOf(next.config)).toEqual(['machine-a2']);
    // Only the newest version's document is kept, under a key that names the version.
    const store = (
      sessions as unknown as { sessions: Map<string, { documents: Map<string, unknown> }> }
    ).sessions;
    const keys = [...(store.get(a.grantId)?.documents.keys() ?? [])];
    expect(keys).toEqual([`${a.grantId}\u00005`]);
  });

  it('re-opens once when the config token lapses, and keeps serving', async () => {
    const { a, account, sessions } = await world();
    await sessions.acquire(a.grantId, a.secret);
    account.expireNextToken = true;
    const again = await sessions.acquire(a.grantId, a.secret);
    expect(machinesOf(again.config)).toEqual(['machine-a']);
    expect(account.count('POST /configs/agent-session')).toBe(2);
  });

  it('reports an unavailable account as unavailable, not as a refusal, and keeps a warm session', async () => {
    const { a, b, account, sessions } = await world();
    await sessions.acquire(a.grantId, a.secret);
    account.failNextOpenWith = 503;
    await expect(sessions.acquire(b.grantId, b.secret)).rejects.toBeInstanceOf(
      AgentSessionUnavailable
    );
    expect(sessions.has(a.grantId)).toBe(true);
    expect(sessions.has(b.grantId)).toBe(false);
  });

  it('stops serving a session past the grant expiry', async () => {
    const grant = await makeGrant({
      grantId: 'g_short',
      configId: 'cfg-s',
      machine: 'm',
      expiresAt: new Date(Date.now() + 1000).toISOString(),
    });
    const account: FakeAccount = fakeAccount([grant]);
    let now = Date.now();
    const sessions = new AgentGrantSessions({
      accountUrl: 'https://account.test',
      executorToken: EXECUTOR_TOKEN,
      orgId: ORG_ID,
      fetchImpl: account.fetch,
      now: () => now,
    });
    const handle = await sessions.acquire(grant.grantId, grant.secret);
    now += 5000;
    expect(() => sessions.currentConfig(handle.principal)).toThrow(SessionError);
    account.refused.add(grant.grantId);
    await expect(sessions.acquire(grant.grantId, grant.secret)).rejects.toBeInstanceOf(
      AgentSessionRefused
    );
  });
});

describe('pushed revocation (box AG-S5)', () => {
  it('drops the session and refuses the next call without asking the account, leaving the other grant alone', async () => {
    const { a, b, account, sessions } = await world();
    const handle = await sessions.acquire(a.grantId, a.secret);
    await sessions.acquire(b.grantId, b.secret);
    const opens = account.count('POST /configs/agent-session');

    expect(sessions.revoke(a.grantId)).toBe(true);

    expect(sessions.has(a.grantId)).toBe(false);
    expect(() => sessions.currentConfig(handle.principal)).toThrow(SessionError);
    await expect(sessions.acquire(a.grantId, a.secret)).rejects.toBeInstanceOf(AgentSessionRefused);
    expect(account.count('POST /configs/agent-session')).toBe(opens);
    expect(sessions.has(b.grantId)).toBe(true);
    expect(machinesOf((await sessions.acquire(b.grantId, b.secret)).config)).toEqual(['machine-b']);
  });

  it('keeps a call that already holds the handle usable, and answers false when no session was held', async () => {
    const { a, sessions } = await world();
    const handle = await sessions.acquire(a.grantId, a.secret);
    sessions.revoke(a.grantId);
    expect(machinesOf(handle.config)).toEqual(['machine-a']);
    expect(sessions.revoke('g_never_opened')).toBe(false);
  });

  it('does not let an open in flight bring the session back', async () => {
    const { a, account, sessions } = await world();
    const { release } = holdOpens(account, sessions);
    const open = sessions.acquire(a.grantId, a.secret).catch((error: unknown) => error);
    await vi.waitFor(() => expect(account.count('POST /configs/agent-session')).toBe(1));
    sessions.revoke(a.grantId);
    release();
    expect(await open).toBeInstanceOf(AgentSessionRefused);
    expect(sessions.has(a.grantId)).toBe(false);
  });

  it('forgets the revocation after the longest grant lifetime', async () => {
    const { a } = await world();
    const account = fakeAccount([a]);
    let now = Date.now();
    const sessions = new AgentGrantSessions({
      accountUrl: 'https://account.test',
      executorToken: EXECUTOR_TOKEN,
      orgId: ORG_ID,
      fetchImpl: account.fetch,
      now: () => now,
    });
    sessions.revoke(a.grantId);
    await expect(sessions.acquire(a.grantId, a.secret)).rejects.toBeInstanceOf(AgentSessionRefused);
    now += 31 * 24 * 60 * 60 * 1000;
    sessions.revoke('g_other');
    expect(machinesOf((await sessions.acquire(a.grantId, a.secret)).config)).toEqual(['machine-a']);
  });
});

describe('routeAgentPrincipals', () => {
  it('sends a grant principal to its session and every other principal to the user loader', async () => {
    const { a, sessions } = await world();
    const handle = await sessions.acquire(a.grantId, a.secret);
    const userConfig = configOf('user-config', 'user-machine');
    const userLoader = vi.fn(() => Promise.resolve(userConfig));
    const load = routeAgentPrincipals(userLoader, sessions);

    expect(machinesOf(await load(handle.principal))).toEqual(['machine-a']);
    expect(userLoader).not.toHaveBeenCalled();

    const human = {
      orgId: ORG_ID,
      teamId: null,
      userId: 'u1',
      userEmail: 'u@x',
      orgRole: 'owner' as const,
    };
    expect(await load(human, 'sess-1')).toBe(userConfig);
    expect(userLoader).toHaveBeenCalledWith(human, 'sess-1');
  });

  it('refuses a grant principal when the executor serves no grants, never falling to the user loader', async () => {
    const userLoader = vi.fn(() => Promise.resolve(configOf('c', 'm')));
    const load = routeAgentPrincipals(userLoader, undefined);
    await expect(load(principalOf('g'))).rejects.toBeInstanceOf(SessionError);
    expect(userLoader).not.toHaveBeenCalled();
  });
});

describe('a team grant in a store with no org-level config (review acee0d10.1)', () => {
  it('refuses the grant and drops its session instead of skipping the org record', async () => {
    const a = await makeGrant({
      grantId: 'g_noorg',
      teamId: 'team-a',
      configId: 'cfg-a',
      machine: 'machine-a',
    });
    const account = fakeAccount([a]);
    // The store lists the team's config and no org-level one.
    const fetchImpl: typeof fetch = async (input, init) => {
      const response = await account.fetch(input, init);
      const url = new URL(typeof input === 'string' ? input : (input as Request).url);
      if (url.pathname.endsWith('/configs') && init?.method === 'GET') {
        const body = (await response.json()) as { configs: { teamId: string | null }[] };
        return new Response(
          JSON.stringify({ ...body, configs: body.configs.filter((c) => c.teamId !== null) }),
          { status: response.status, headers: { 'content-type': 'application/json' } }
        );
      }
      return response;
    };
    const sessions = new AgentGrantSessions({
      accountUrl: 'https://account.test',
      executorToken: EXECUTOR_TOKEN,
      orgId: ORG_ID,
      fetchImpl,
    });
    await expect(sessions.acquire(a.grantId, a.secret)).rejects.toBeInstanceOf(AgentSessionRefused);
    expect(sessions.has(a.grantId)).toBe(false);
  });
});

describe('daemon-mode revoke route (box AG-OP1)', () => {
  async function daemon(role: 'owner' | 'admin' | 'member' = 'admin', orgId = ORG_ID) {
    const { a, b, sessions } = await world();
    const deps = {
      mode: 'daemon',
      auth: {
        verify: (token: string) =>
          token === 'good'
            ? Promise.resolve({ orgId, teamId: null, userId: 'u', userEmail: 'u@x', orgRole: role })
            : Promise.reject(new AuthError('bad token', 401)),
      } as unknown as ServeDeps['auth'],
      sessions: new SessionStore(),
      crypto: serveCrypto,
      agentGrants: sessions,
    } as unknown as ServeDeps;
    const app = createServeApp(deps);
    const post = (body: unknown, token = 'good') =>
      app.request(PROXY_ROUTES.mcpRevoke, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          ...(token ? { authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
      });
    return { a, b, sessions, post };
  }

  it('drops the named grant for an org admin and leaves the other grant alone', async () => {
    const { a, b, sessions, post } = await daemon();
    await sessions.acquire(a.grantId, a.secret);
    await sessions.acquire(b.grantId, b.secret);
    const response = await post({ grantId: a.grantId });
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ dropped: true });
    expect(sessions.has(a.grantId)).toBe(false);
    expect(sessions.has(b.grantId)).toBe(true);
    await expect(sessions.acquire(a.grantId, a.secret)).rejects.toBeInstanceOf(AgentSessionRefused);
  });

  it('refuses no bearer, an unknown bearer, a member and another org, each leaving the session held', async () => {
    const { a, sessions, post } = await daemon();
    await sessions.acquire(a.grantId, a.secret);
    expect((await post({ grantId: a.grantId }, '')).status).toBe(401);
    expect((await post({ grantId: a.grantId }, 'nope')).status).toBe(401);
    expect(sessions.has(a.grantId)).toBe(true);
    for (const world of [await daemon('member'), await daemon('owner', 'org-other')]) {
      await world.sessions.acquire(world.a.grantId, world.a.secret);
      expect((await world.post({ grantId: world.a.grantId })).status).toBe(403);
      expect(world.sessions.has(world.a.grantId)).toBe(true);
    }
  });

  it('refuses a malformed body', async () => {
    const { post } = await daemon();
    expect((await post({ grantId: 'a b' })).status).toBe(400);
    expect((await post({ grantId: 'g', extra: 1 })).status).toBe(400);
  });
});
