/**
 * The daemon's environment scope: a client whose principal, server or
 * agent-mode switches differ from a daemon's reaches a daemon of its own.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { daemonSocketPath, environmentIdentity } from '../daemon/lifecycle.js';

const base = {
  REDIACC_TOKEN: 'token-a',
  REDIACC_ACCOUNT_SERVER: 'http://localhost:4800',
  HOME: '/home/x',
};

describe('daemon environment identity', () => {
  it('differs when the token differs (the vm:check re-seed, 2026-10-15)', () => {
    expect(environmentIdentity({ ...base, REDIACC_TOKEN: 'token-b' })).not.toBe(
      environmentIdentity(base)
    );
  });

  it('differs when the account server or an agent-mode switch differs', () => {
    const id = environmentIdentity(base);
    expect(
      environmentIdentity({ ...base, REDIACC_ACCOUNT_SERVER: 'https://eu.rediacc.com' })
    ).not.toBe(id);
    expect(environmentIdentity({ ...base, REDIACC_AGENT: '1' })).not.toBe(id);
    expect(environmentIdentity({ ...base, REDIACC_ALLOW_GRAND_REPO: '1' })).not.toBe(id);
  });

  it("ignores the daemon's own plumbing and every non-REDIACC variable", () => {
    const id = environmentIdentity(base);
    // The daemon sets REDIACC_SSH_LINGER_MS on itself before taking its identity, so counting it would make every hello stale.
    expect(environmentIdentity({ ...base, REDIACC_SSH_LINGER_MS: '300000' })).toBe(id);
    expect(environmentIdentity({ ...base, REDIACC_VIA_DAEMON: '1' })).toBe(id);
    expect(environmentIdentity({ ...base, REDIACC_NO_DAEMON: '0' })).toBe(id);
    expect(environmentIdentity({ ...base, HOME: '/elsewhere', PATH: '/bin' })).toBe(id);
  });

  it('carries no value, only a fixed-length digest', () => {
    const id = environmentIdentity(base);
    expect(id).toMatch(/^[0-9a-f]{16}$/);
    expect(id).not.toContain('token-a');
  });
});

describe('daemon socket scope', () => {
  const saved = process.env.REDIACC_TOKEN;
  afterEach(() => {
    if (saved === undefined) delete process.env.REDIACC_TOKEN;
    else process.env.REDIACC_TOKEN = saved;
  });

  it('gives a client with another REDIACC environment another socket, so neither evicts the other (review b3e07699.1)', () => {
    process.env.REDIACC_TOKEN = 'token-a';
    const a = daemonSocketPath();
    process.env.REDIACC_TOKEN = 'token-b';
    const b = daemonSocketPath();
    expect(b).not.toBe(a);
    process.env.REDIACC_TOKEN = 'token-a';
    expect(daemonSocketPath()).toBe(a);
  });
});
