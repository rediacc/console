/**
 * Design 2 of PLAN-rmcp-executor-hardening: a verifier cache entry never outlives
 * the token's own expiry, and the cache holds at most 1,024 identities.
 */

import { describe, expect, it, vi } from 'vitest';
import { AuthVerifier, VERIFIER_CACHE_MAX_ENTRIES } from '../auth.js';

function identity(expiresAt?: string) {
  return {
    active: true,
    scopes: ['proxy:exec'],
    orgId: 'org-a',
    teamId: null,
    createdByUserId: 'user-1',
    userEmail: 'u@example.com',
    orgRole: 'member',
    tokenId: 'tok-1',
    ...(expiresAt === undefined ? {} : { expiresAt }),
  };
}

function verifier(fetchImpl: typeof fetch, now: () => number): AuthVerifier {
  return new AuthVerifier({
    accountUrl: 'https://account.test',
    executorToken: 'rdt_executor',
    fetchImpl,
    now,
  });
}

describe('verifier cache expiry cap', () => {
  it('re-introspects a token expiring in 5 s once those 5 s have passed', async () => {
    let clock = 1_000_000;
    const expiresAt = new Date(clock + 5_000).toISOString();
    const fetchImpl = vi.fn(() => Promise.resolve(Response.json(identity(expiresAt))));
    const v = verifier(fetchImpl as unknown as typeof fetch, () => clock);

    await v.verify('t');
    clock += 4_000;
    await v.verify('t');
    expect(fetchImpl).toHaveBeenCalledTimes(1);

    clock += 1_001;
    // The token is now past its expiry: re-introspected, and refused even though the server still says active.
    await expect(v.verify('t')).rejects.toThrow(/not valid for the executor/);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('keeps a token with no expiry for the full minute (control)', async () => {
    let clock = 1_000_000;
    const fetchImpl = vi.fn(() => Promise.resolve(Response.json(identity())));
    const v = verifier(fetchImpl as unknown as typeof fetch, () => clock);

    await v.verify('t');
    clock += 59_000;
    await v.verify('t');
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    clock += 1_001;
    await v.verify('t');
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('refuses an active token whose expiresAt is at or before now, and does not cache it', async () => {
    const clock = 1_000_000;
    for (const offset of [-1_000, 0]) {
      const expiresAt = new Date(clock + offset).toISOString();
      const fetchImpl = vi.fn(() => Promise.resolve(Response.json(identity(expiresAt))));
      const v = verifier(fetchImpl as unknown as typeof fetch, () => clock);
      await expect(v.verify('t')).rejects.toThrow(/not valid for the executor/);
      await expect(v.verify('t')).rejects.toThrow(/not valid for the executor/);
      expect(fetchImpl).toHaveBeenCalledTimes(2);
      expect(v.cacheSize).toBe(0);
    }
  });

  it('accepts and caches an active token expiring in the future (control)', async () => {
    const clock = 1_000_000;
    const expiresAt = new Date(clock + 30_000).toISOString();
    const fetchImpl = vi.fn(() => Promise.resolve(Response.json(identity(expiresAt))));
    const v = verifier(fetchImpl as unknown as typeof fetch, () => clock);
    await expect(v.verify('t')).resolves.toMatchObject({ userId: 'user-1' });
    await v.verify('t');
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(v.cacheSize).toBe(1);
  });

  it('refuses an unreadable expiry instead of caching it', async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(Response.json(identity('not-a-date'))));
    const v = verifier(fetchImpl as unknown as typeof fetch, () => 1_000_000);
    await expect(v.verify('t')).rejects.toThrow(/unreadable expiry/);
    expect(v.cacheSize).toBe(0);
  });
});

describe('verifier cache bound', () => {
  it('never holds more than 1,024 entries under 5,000 distinct bearers', async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(Response.json(identity())));
    const v = verifier(fetchImpl as unknown as typeof fetch, () => 1_000_000);
    let peak = 0;
    for (let i = 0; i < 5_000; i++) {
      await v.verify(`bearer-${i}`);
      peak = Math.max(peak, v.cacheSize);
    }
    expect(VERIFIER_CACHE_MAX_ENTRIES).toBe(1_024);
    expect(peak).toBe(VERIFIER_CACHE_MAX_ENTRIES);
  });

  it('evicts the least recently used entry, not a recently read one', async () => {
    const fetchImpl = vi.fn(() => Promise.resolve(Response.json(identity())));
    const v = verifier(fetchImpl as unknown as typeof fetch, () => 1_000_000);
    await v.verify('hot');
    for (let i = 0; i < VERIFIER_CACHE_MAX_ENTRIES - 1; i++) await v.verify(`cold-${i}`);
    await v.verify('hot'); // a hit: now the most recently used
    await v.verify('newcomer'); // pushes out cold-0, the oldest
    const before = fetchImpl.mock.calls.length;
    await v.verify('hot');
    expect(fetchImpl.mock.calls.length).toBe(before);
    await v.verify('cold-0');
    expect(fetchImpl.mock.calls.length).toBe(before + 1);
  });

  it('drops an expired entry when it is read', async () => {
    let clock = 1_000_000;
    const fetchImpl = vi.fn(() => Promise.resolve(Response.json(identity())));
    const v = verifier(fetchImpl as unknown as typeof fetch, () => clock);
    await v.verify('t');
    expect(v.cacheSize).toBe(1);
    clock += 60_001;
    fetchImpl.mockImplementationOnce(() => Promise.resolve(Response.json({ active: false })));
    await expect(v.verify('t')).rejects.toThrow();
    expect(v.cacheSize).toBe(0);
  });
});
