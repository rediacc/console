/**
 * C1: a container executor is pinned to one org. It refuses to boot unpinned,
 * and refuses a principal of another org exactly like an inactive token, without
 * caching the foreign answer.
 */

import { describe, expect, it, vi } from 'vitest';
import { AuthError, AuthVerifier, resolvePinnedOrgId } from '../auth.js';

function identity(orgId: string) {
  return {
    active: true,
    scopes: ['proxy:exec'],
    orgId,
    teamId: null,
    createdByUserId: 'user-1',
    userEmail: 'u@example.com',
    orgRole: 'member',
    tokenId: 'tok-1',
  };
}

function verifier(fetchImpl: typeof fetch, pinnedOrgId?: string): AuthVerifier {
  return new AuthVerifier({
    accountUrl: 'https://account.test',
    executorToken: 'rdt_executor',
    pinnedOrgId,
    fetchImpl,
  });
}

describe('pinned org boot', () => {
  it('refuses container mode without REDIACC_EXECUTOR_ORG_ID', () => {
    expect(() => resolvePinnedOrgId('container', {})).toThrow(/REDIACC_EXECUTOR_ORG_ID/);
    expect(() => resolvePinnedOrgId('container', { REDIACC_EXECUTOR_ORG_ID: '  ' })).toThrow(
      /REDIACC_EXECUTOR_ORG_ID/
    );
  });

  it('returns the pinned org, and none for daemon mode', () => {
    expect(resolvePinnedOrgId('container', { REDIACC_EXECUTOR_ORG_ID: 'org-a' })).toBe('org-a');
    expect(resolvePinnedOrgId('daemon', {})).toBeUndefined();
  });
});

describe('pinned org verification', () => {
  it('accepts a principal of the pinned org', async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(Response.json(identity('org-a'))));
    const principal = await verifier(fetchImpl as unknown as typeof fetch, 'org-a').verify('t');
    expect(principal.orgId).toBe('org-a');
  });

  it('refuses a foreign org with the inactive-token 401', async () => {
    const foreign = vi.fn(() => Promise.resolve(Response.json(identity('org-b'))));
    const inactive = vi.fn(() => Promise.resolve(Response.json({ active: false })));
    const a = await verifier(foreign as unknown as typeof fetch, 'org-a')
      .verify('t')
      .catch((e: unknown) => e);
    const b = await verifier(inactive as unknown as typeof fetch, 'org-a')
      .verify('t')
      .catch((e: unknown) => e);
    expect(a).toBeInstanceOf(AuthError);
    expect((a as AuthError).status).toBe(401);
    expect((a as AuthError).message).toBe((b as AuthError).message);
    expect((b as AuthError).status).toBe(401);
  });

  it('does not cache a foreign-org answer', async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(Response.json(identity('org-b'))));
    const v = verifier(fetchImpl as unknown as typeof fetch, 'org-a');
    await expect(v.verify('t')).rejects.toBeInstanceOf(AuthError);
    await expect(v.verify('t')).rejects.toBeInstanceOf(AuthError);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('takes any org when unpinned (daemon)', async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(Response.json(identity('org-b'))));
    const principal = await verifier(fetchImpl as unknown as typeof fetch).verify('t');
    expect(principal.orgId).toBe('org-b');
  });
});
