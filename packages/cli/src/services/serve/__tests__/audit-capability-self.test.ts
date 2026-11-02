/**
 * P2: the audit self-check asks the account server about the executor token
 * with `{ token, self: true }`, and a server that only understands the legacy
 * shape (it strips `self` and reads `token`) still yields the capability.
 */

import { describe, expect, it, vi } from 'vitest';
import { AuthVerifier } from '../auth.js';

const EXECUTOR_TOKEN = 'rdt_executor';

function identity(scopes: string[]) {
  return {
    active: true,
    scopes,
    orgId: 'org-1',
    teamId: null,
    createdByUserId: 'user-exec',
    userEmail: 'exec@example.com',
    orgRole: 'owner',
  };
}

function verifier(fetchImpl: typeof fetch): AuthVerifier {
  return new AuthVerifier({
    accountUrl: 'https://account.test',
    executorToken: EXECUTOR_TOKEN,
    fetchImpl,
  });
}

describe('audit capability self-check', () => {
  it('sends { token, self: true } with the executor bearer', async () => {
    const fetchImpl = vi.fn(() =>
      Promise.resolve(Response.json(identity(['proxy:exec', 'audit:write'])))
    );
    const result = await verifier(fetchImpl as unknown as typeof fetch).canWriteAudit();

    expect(result).toEqual({ ok: true });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('https://account.test/account/api/v1/proxy/introspect');
    expect(JSON.parse(String(init.body))).toEqual({ token: EXECUTOR_TOKEN, self: true });
    expect((init.headers as Record<string, string>).authorization).toBe(`Bearer ${EXECUTOR_TOKEN}`);
  });

  it('still yields the capability from a server that answers only the legacy shape', async () => {
    // A legacy server strips the unknown key and introspects `token`.
    const legacy = vi.fn((_url: string | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>;
      const { token } = body;
      return Promise.resolve(
        Response.json(
          token === EXECUTOR_TOKEN ? identity(['proxy:exec', 'audit:write']) : { active: false }
        )
      );
    });
    const result = await verifier(legacy as unknown as typeof fetch).canWriteAudit();

    expect(result).toEqual({ ok: true });
  });

  it('reports a missing audit:write scope', async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(Response.json(identity(['proxy:exec']))));
    const result = await verifier(fetchImpl as unknown as typeof fetch).canWriteAudit();

    expect(result.ok).toBe(false);
  });
});
