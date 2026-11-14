/**
 * The headless password login requests `delegation:issue` (so `rdc server install` can mint the
 * delegation cert) alongside the other privileged scopes, and drops it for a plain member.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../i18n/index.js', () => ({ t: (key: string) => key }));
vi.mock('../../core/output.js', () => ({ outputService: { warn: vi.fn() } }));

import { loginWithPassword } from '../subscription-password-auth.js';

interface Call {
  url: string;
  scopes?: string[];
}

function reply(status: number, body: unknown, cookie?: string): Response {
  return {
    status,
    headers: { getSetCookie: () => (cookie ? [`access_token=${cookie}; Path=/`] : []) },
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

/** A server that refuses the first (privileged) mint with `refusal`, if given, then accepts. */
function stubServer(refusal?: { status: number; body: unknown }): Call[] {
  const calls: Call[] = [];
  let mints = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: { body?: string }) => {
      const body = init?.body ? (JSON.parse(init.body) as { scopes?: string[] }) : {};
      calls.push({ url, scopes: body.scopes });
      if (url.endsWith('/auth/login')) return reply(200, {}, 'sess');
      if (url.endsWith('/portal/me')) return reply(200, { subscription: { id: 'sub' } });
      mints += 1;
      if (refusal && mints === 1) return reply(refusal.status, refusal.body);
      return reply(200, { token: 'tok' });
    })
  );
  return calls;
}

const mintScopes = (calls: Call[]) =>
  calls.filter((c) => c.url.endsWith('/api-tokens')).map((c) => c.scopes ?? []);

afterEach(() => vi.unstubAllGlobals());

describe('loginWithPassword scopes', () => {
  it('requests delegation:issue with the privileged scopes', async () => {
    const calls = stubServer();
    await expect(loginWithPassword('https://srv', { email: 'a@b.c', password: 'p' })).resolves.toBe(
      'tok'
    );
    const [first] = mintScopes(calls);
    expect(first).toEqual(
      expect.arrayContaining(['delegation:issue', 'backup:manage', 'audit:write'])
    );
  });

  it('drops delegation:issue when the account is a plain member', async () => {
    const calls = stubServer({ status: 403, body: { code: 'INSUFFICIENT_ORG_ROLE' } });
    await loginWithPassword('https://srv', { email: 'a@b.c', password: 'p' });
    const [, retry] = mintScopes(calls);
    expect(retry).toContain('license:activate');
    expect(retry).not.toContain('delegation:issue');
    expect(retry).not.toContain('backup:manage');
  });

  it('drops delegation:issue together with backup:manage when 2FA is missing', async () => {
    const calls = stubServer({ status: 403, body: { twoFactorRequired: true } });
    await loginWithPassword('https://srv', { email: 'a@b.c', password: 'p' });
    const [, retry] = mintScopes(calls);
    expect(retry).toContain('audit:write');
    expect(retry).not.toContain('delegation:issue');
    expect(retry).not.toContain('backup:manage');
  });
});
