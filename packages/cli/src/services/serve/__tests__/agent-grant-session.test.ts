/**
 * Agent-grant sessions (agent/plans/PLAN-rmcp-agent-grants.md box AG-X, Design 4): one session per grant, rebuilt from the
 * secret after a sleep, with the secret never held. The account server is a fake with real ciphertext (agent-grant-harness.ts).
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  AgentGrantSessions,
  AgentSessionRefused,
  AgentSessionUnavailable,
} from '../agent-grant-session.js';
import { routeAgentPrincipals } from '../container-config.js';
import { SessionError } from '../sessions.js';
import {
  configOf,
  EXECUTOR_TOKEN,
  type FakeAccount,
  fakeAccount,
  makeGrant,
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
