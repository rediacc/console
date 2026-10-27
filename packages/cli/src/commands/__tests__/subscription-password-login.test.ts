/**
 * Headless account login (`rdc subscription login` with REDIACC_LOGIN_EMAIL + REDIACC_LOGIN_PASSWORD
 * or --password-stdin) and `rdc config remote enable --master-password-stdin`: the secrets come from the
 * environment or stdin, and no secret appears in anything printed.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { mockReadStdinValue } = vi.hoisted(() => ({ mockReadStdinValue: vi.fn() }));

vi.mock('../../utils/stdin.js', () => ({ readStdinValue: mockReadStdinValue }));
vi.mock('../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, string | number>) =>
    vars ? `${key}:${Object.values(vars).join(':')}` : key,
}));

const { loginWithPassword, resolvePasswordLoginInput, wantsPasswordLogin } = await import(
  '../../services/account/subscription-password-auth.js'
);

const SERVER = 'https://account.example.com';
const PASSWORD = 'pw-SECRET-value-1';
const CODE = '987654';
const COOKIE = 'access_token=sess-abc';
const ENV_KEYS = ['REDIACC_LOGIN_EMAIL', 'REDIACC_LOGIN_PASSWORD', 'REDIACC_LOGIN_TOTP'];

function reply(body: unknown, status = 200, cookie?: string): Response {
  const headers = new Headers({ 'Content-Type': 'application/json' });
  if (cookie) headers.append('Set-Cookie', `${cookie}; Path=/; HttpOnly`);
  return new Response(JSON.stringify(body), { status, headers });
}

interface Call {
  url: string;
  body?: Record<string, unknown>;
  cookie?: string;
}

type Opts = { twoFactor?: boolean; memberRefusedPrivileged?: boolean };

function route(path: string, body: Record<string, unknown> | undefined, opts: Opts): Response {
  if (path === '/auth/login') {
    return opts.twoFactor
      ? reply({ requiresTwoFactor: true, challengeToken: 'chal-1' })
      : reply({ user: {} }, 200, COOKIE);
  }
  if (path === '/auth/2fa/verify') return reply({ user: {} }, 200, COOKIE);
  if (path === '/portal/me') {
    return reply({ subscription: { id: 'sub-1' }, activeTeam: { id: 'team-1' } });
  }
  if (path === '/api-tokens') {
    const scopes = (body?.scopes ?? []) as string[];
    return opts.memberRefusedPrivileged && scopes.includes('audit:write')
      ? reply({ error: 'no', code: 'INSUFFICIENT_ORG_ROLE' }, 403)
      : reply({ token: 'rdt_minted' }, 201);
  }
  return reply({ error: 'unexpected' }, 404);
}

function stubServer(opts: Opts) {
  const calls: Call[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      const path = url.replace(`${SERVER}/account/api/v1`, '');
      const headers = (init?.headers ?? {}) as Record<string, string>;
      const body = init?.body
        ? (JSON.parse(String(init.body)) as Record<string, unknown>)
        : undefined;
      calls.push({ url: path, body, cookie: headers.Cookie });
      return Promise.resolve(route(path, body, opts));
    })
  );
  return calls;
}

describe('headless subscription login', () => {
  const saved: Record<string, string | undefined> = {};
  beforeEach(() => {
    vi.clearAllMocks();
    for (const k of ENV_KEYS) {
      saved[k] = process.env[k];
      delete process.env[k];
    }
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    for (const k of ENV_KEYS) {
      if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    }
  });

  it('is selected by the env pair or by --password-stdin only', () => {
    expect(wantsPasswordLogin(false)).toBe(false);
    process.env.REDIACC_LOGIN_EMAIL = 'a@b.co';
    expect(wantsPasswordLogin(false)).toBe(false);
    process.env.REDIACC_LOGIN_PASSWORD = PASSWORD;
    expect(wantsPasswordLogin(false)).toBe(true);
    delete process.env.REDIACC_LOGIN_PASSWORD;
    expect(wantsPasswordLogin(true)).toBe(true);
  });

  it('logs in from the environment without 2FA and mints with the device scopes', async () => {
    process.env.REDIACC_LOGIN_EMAIL = 'a@b.co';
    process.env.REDIACC_LOGIN_PASSWORD = PASSWORD;
    const calls = stubServer({});
    const input = await resolvePasswordLoginInput(false);
    await expect(loginWithPassword(SERVER, input)).resolves.toBe('rdt_minted');
    expect(calls.map((c) => c.url)).toEqual(['/auth/login', '/portal/me', '/api-tokens']);
    expect(calls[0].body).toEqual({ email: 'a@b.co', password: PASSWORD });
    const mint = calls[2];
    expect(mint.cookie).toBe(COOKIE);
    expect(mint.body?.subscriptionId).toBe('sub-1');
    expect(mint.body?.scopes).toContain('config:enroll');
  });

  it('completes 2FA with REDIACC_LOGIN_TOTP', async () => {
    process.env.REDIACC_LOGIN_EMAIL = 'a@b.co';
    process.env.REDIACC_LOGIN_PASSWORD = PASSWORD;
    process.env.REDIACC_LOGIN_TOTP = CODE;
    const calls = stubServer({ twoFactor: true });
    const input = await resolvePasswordLoginInput(false);
    await expect(loginWithPassword(SERVER, input)).resolves.toBe('rdt_minted');
    expect(calls[1]).toMatchObject({
      url: '/auth/2fa/verify',
      body: { challengeToken: 'chal-1', code: CODE },
    });
  });

  it('refuses with a named error when 2FA is required and no code is given', async () => {
    process.env.REDIACC_LOGIN_EMAIL = 'a@b.co';
    process.env.REDIACC_LOGIN_PASSWORD = PASSWORD;
    const calls = stubServer({ twoFactor: true });
    const input = await resolvePasswordLoginInput(false);
    const err = await loginWithPassword(SERVER, input).catch((e: Error) => e);
    expect((err as Error).message).toContain('REDIACC_LOGIN_TOTP');
    expect(calls.map((c) => c.url)).toEqual(['/auth/login']);
  });

  it('retries the mint without privileged scopes for a plain member', async () => {
    process.env.REDIACC_LOGIN_EMAIL = 'a@b.co';
    process.env.REDIACC_LOGIN_PASSWORD = PASSWORD;
    const calls = stubServer({ memberRefusedPrivileged: true });
    const input = await resolvePasswordLoginInput(false);
    await expect(loginWithPassword(SERVER, input)).resolves.toBe('rdt_minted');
    const mints = calls.filter((c) => c.url === '/api-tokens');
    expect(mints).toHaveLength(2);
    expect(mints[1].body?.scopes).not.toContain('audit:write');
    expect(mints[1].body?.scopes).toContain('config:enroll');
  });

  it('reads the password from stdin under --password-stdin', async () => {
    process.env.REDIACC_LOGIN_EMAIL = 'a@b.co';
    mockReadStdinValue.mockResolvedValue(PASSWORD);
    const input = await resolvePasswordLoginInput(true);
    expect(input.password).toBe(PASSWORD);
  });

  it('names the missing field, never a value', async () => {
    await expect(resolvePasswordLoginInput(false)).rejects.toThrow('REDIACC_LOGIN_EMAIL');
    process.env.REDIACC_LOGIN_EMAIL = 'a@b.co';
    mockReadStdinValue.mockResolvedValue('');
    await expect(resolvePasswordLoginInput(true)).rejects.toThrow('--password-stdin');
  });

  it('keeps the password and code out of every error it raises', async () => {
    process.env.REDIACC_LOGIN_EMAIL = 'a@b.co';
    process.env.REDIACC_LOGIN_PASSWORD = PASSWORD;
    process.env.REDIACC_LOGIN_TOTP = CODE;
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(reply({ error: 'Invalid credentials' }, 401)))
    );
    const input = await resolvePasswordLoginInput(false);
    const err = (await loginWithPassword(SERVER, input).catch((e: Error) => e)) as Error;
    expect(err.message).toContain('login');
    expect(err.message).not.toContain(PASSWORD);
    expect(err.message).not.toContain(CODE);
  });
});
