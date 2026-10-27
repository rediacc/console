/**
 * `rdc config remote password change`: the master password slot is rebuilt from this device's CEK.
 *
 * Crypto is REAL: a genuine CEK and serverSecret, the slot built by the command, PUT to a fake
 * server that keeps it, and the verify reads it back through passwordCredentials (the code
 * `enable --password` runs) and unwraps it with PBKDF2 + HKDF + AES-GCM. Only I/O is mocked:
 * fetch (the cookie session), accountServerFetch (password-enroll), the adapter's enrollment.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const STORE_ID = '11111111-1111-4111-8111-111111111111';
const CONFIG_ID = '22222222-2222-4222-8222-222222222222';
const API = 'https://account.example.com';

const NEW_PASSWORD = 'NEW-master-SECRET-pw';
const LOGIN_PASSWORD = 'LOGIN-account-SECRET';
const LOGIN_TOTP = '111111';
const NEXT_TOTP = '222222';

const { state, mockAccountServerFetch, mockReadStdinValue, mockAskInput, mockAskPassword, said } =
  vi.hoisted(() => ({
    state: {
      cek: undefined as CryptoKey | undefined,
      serverSecret: undefined as Uint8Array | undefined,
      slot: undefined as { kdfParams: unknown; wrappedCek: string } | undefined,
      elevated: false,
      putStatus: 200,
      putError: undefined as string | undefined,
      reauthStatus: 200,
      calls: [] as string[],
      pulls: 0,
    },
    mockAccountServerFetch: vi.fn(),
    mockReadStdinValue: vi.fn(),
    mockAskInput: vi.fn(),
    mockAskPassword: vi.fn(),
    said: [] as string[],
  }));

vi.mock('../../services/account/account-client.js', () => ({
  accountServerFetch: mockAccountServerFetch,
}));
vi.mock('../../utils/stdin.js', () => ({ readStdinValue: mockReadStdinValue }));
vi.mock('../../utils/prompt.js', () => ({
  askInput: mockAskInput,
  askPassword: mockAskPassword,
  askConfirm: vi.fn(),
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    success: (m: string) => said.push(m),
    info: (m: string) => said.push(m),
    warn: (m: string) => said.push(m),
  },
}));
vi.mock('../../utils/spinner.js', () => ({
  withSpinner: async <T>(start: string, fn: () => Promise<T>, done: string) => {
    said.push(start);
    const out = await fn();
    said.push(done);
    return out;
  },
}));
vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: {
    load: () =>
      Promise.resolve({
        schemaVersion: 3,
        id: 'cfg',
        version: 1,
        remote: { apiUrl: API, storeId: STORE_ID, configId: CONFIG_ID, storageKeyId: 'rdc:k' },
      }),
  },
}));
vi.mock('../../adapters/remote-token-storage.js', () => ({ remoteTokenStorage: {} }));
vi.mock('../../utils/secure-storage.js', () => ({ getSecureStorage: () => ({}) }));
vi.mock('../../adapters/remote-config-adapter.js', () => ({
  RemoteStaleSlotError: class RemoteStaleSlotError extends Error {},
  RemoteConfigAdapter: class {
    pull() {
      state.pulls++;
      return Promise.resolve({ config: {}, version: 1 });
    }
    unlockKeyMaterial() {
      return Promise.resolve({ cek: state.cek, serverSecret: state.serverSecret });
    }
  },
}));

const crypto = await import('@rediacc/shared/config-crypto');
const mod = await import('../config-remote-password-change.js');

function json(status: number, body: unknown, setCookie?: string): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: setCookie ? { 'set-cookie': setCookie } : {},
  });
}

type Body = Record<string, unknown>;
const INVALID = { error: 'Invalid verification code' };

function reauthTotp(body: Body): Response {
  if (state.reauthStatus !== 200) return json(state.reauthStatus, INVALID);
  state.elevated = body.code === NEXT_TOTP;
  return state.elevated ? json(200, { elevated: true }) : json(400, INVALID);
}

function putPasswordSlot(body: Body): Response {
  if (state.putStatus !== 200) return json(state.putStatus, { error: state.putError });
  if (!state.elevated) return json(403, { error: 'Re-authentication required' });
  state.slot = { kdfParams: body.kdfParams, wrappedCek: String(body.wrappedCek) };
  return json(200, { success: true });
}

/** Routes that need no cookie. */
const OPEN_ROUTES: Record<string, (body: Body) => Response> = {
  'POST /auth/login': () => json(200, { requiresTwoFactor: true, challengeToken: 'ch' }),
  'POST /auth/2fa/verify': (body) =>
    body.code === LOGIN_TOTP
      ? json(200, {}, 'access_token=sess; Path=/; HttpOnly')
      : json(400, INVALID),
};

/** Routes behind the access_token cookie. */
const SESSION_ROUTES: Record<string, (body: Body) => Response> = {
  'GET /auth/reauth/status': () => json(200, { elevated: state.elevated }),
  'POST /auth/reauth/totp': reauthTotp,
  'PUT /configs/slots/password': putPasswordSlot,
};

/** The account server's cookie-session surface. */
function fakeFetch(input: string | URL, init: RequestInit = {}): Promise<Response> {
  const key = `${init.method ?? 'GET'} ${String(input).replace(`${API}/account/api/v1`, '')}`;
  state.calls.push(key);
  const body = (init.body ? JSON.parse(String(init.body)) : {}) as Body;
  const cookie = (init.headers as Record<string, string | undefined> | undefined)?.Cookie;
  const open = OPEN_ROUTES[key];
  if (open) return Promise.resolve(open(body));
  if (cookie !== 'access_token=sess') {
    return Promise.resolve(json(401, { error: 'Not authenticated' }));
  }
  const route = SESSION_ROUTES[key] as ((body: Body) => Response) | undefined;
  return Promise.resolve(route ? route(body) : json(404, { error: 'no route' }));
}

const written: string[] = [];

beforeEach(async () => {
  vi.clearAllMocks();
  said.length = 0;
  written.length = 0;
  Object.assign(state, {
    cek: await crypto.generateCek(),
    serverSecret: crypto.generateServerSecret(),
    slot: undefined,
    elevated: false,
    putStatus: 200,
    putError: undefined,
    reauthStatus: 200,
    calls: [],
    pulls: 0,
  });
  Object.defineProperty(process.stdin, 'isTTY', { value: false, configurable: true });
  vi.stubGlobal('fetch', vi.fn(fakeFetch));
  vi.stubEnv('REDIACC_LOGIN_EMAIL', 'ops@example.com');
  vi.stubEnv('REDIACC_LOGIN_PASSWORD', LOGIN_PASSWORD);
  vi.stubEnv('REDIACC_LOGIN_TOTP', LOGIN_TOTP);
  vi.stubEnv('REDIACC_LOGIN_TOTP_NEXT', NEXT_TOTP);
  vi.stubEnv('REDIACC_NEW_CONFIG_PASSWORD', '');
  mockAccountServerFetch.mockImplementation((path: string) => {
    if (path !== '/account/api/v1/configs/password-enroll' || !state.slot) {
      return Promise.reject(Object.assign(new Error('Not found'), { status: 404 }));
    }
    return Promise.resolve({
      method: 'password',
      kdfParams: state.slot.kdfParams,
      wrappedCek: state.slot.wrappedCek,
      token: 'cfg-token',
      storeId: STORE_ID,
      configId: CONFIG_ID,
      teamId: null,
    });
  });
  const capture = (chunk: unknown) => {
    written.push(String(chunk));
    return true;
  };
  vi.spyOn(process.stdout, 'write').mockImplementation(capture);
  vi.spyOn(process.stderr, 'write').mockImplementation(capture);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function allOutput(): string {
  return [...said, ...written].join('\n');
}

function expectNoSecret(text: string): void {
  for (const secret of [NEW_PASSWORD, LOGIN_PASSWORD, NEXT_TOTP, 'access_token=sess']) {
    expect(text).not.toContain(secret);
  }
}

describe('buildPasswordSlot', () => {
  it('round-trips: the new password and the serverSecret unwrap the same CEK', async () => {
    const cek = state.cek as CryptoKey;
    const serverSecret = state.serverSecret as Uint8Array;
    const slot = await mod.buildPasswordSlot(cek, NEW_PASSWORD, serverSecret);
    expect(slot.kdfParams).toMatchObject({
      method: 'password',
      algorithm: 'PBKDF2-SHA256',
      iterations: crypto.PASSWORD_PBKDF2_ITERATIONS,
    });
    const secret = await crypto.derivePasswordSlotSecret(NEW_PASSWORD, slot.kdfParams);
    const back = await crypto.unwrapCekForSlot(slot.wrappedCek, secret, serverSecret);
    expect(await crypto.exportAesKey(back)).toEqual(await crypto.exportAesKey(cek));

    const wrong = await crypto.derivePasswordSlotSecret('not-the-password', slot.kdfParams);
    await expect(crypto.unwrapCekForSlot(slot.wrappedCek, wrong, serverSecret)).rejects.toThrow();
  });
});

describe('slotOpensCek', () => {
  it('accepts a slot that opens this CEK and refuses one that does not, before any PUT', async () => {
    const cek = state.cek as CryptoKey;
    const serverSecret = state.serverSecret as Uint8Array;
    const slot = await mod.buildPasswordSlot(cek, NEW_PASSWORD, serverSecret);
    expect(await mod.slotOpensCek(slot, NEW_PASSWORD, { cek, serverSecret })).toBe(true);
    expect(await mod.slotOpensCek(slot, 'not-the-password', { cek, serverSecret })).toBe(false);
    const other = await crypto.generateCek();
    expect(await mod.slotOpensCek(slot, NEW_PASSWORD, { cek: other, serverSecret })).toBe(false);
  });
});

describe('resolveNewPassword', () => {
  it('reads stdin under --new-password-stdin', async () => {
    mockReadStdinValue.mockResolvedValue(NEW_PASSWORD);
    await expect(mod.resolveNewPassword(true)).resolves.toBe(NEW_PASSWORD);
  });

  it('refuses an empty stdin by naming the flag', async () => {
    mockReadStdinValue.mockResolvedValue('');
    await expect(mod.resolveNewPassword(true)).rejects.toThrow('--new-password-stdin');
  });

  it('reads REDIACC_NEW_CONFIG_PASSWORD without stdin', async () => {
    vi.stubEnv('REDIACC_NEW_CONFIG_PASSWORD', NEW_PASSWORD);
    await expect(mod.resolveNewPassword(false)).resolves.toBe(NEW_PASSWORD);
    expect(mockReadStdinValue).not.toHaveBeenCalled();
  });

  it('names both inputs when neither is given off a TTY', async () => {
    const error = await mod.resolveNewPassword(false).catch((e: Error) => e);
    expect((error as Error).message).toContain('--new-password-stdin');
    expect((error as Error).message).toContain('REDIACC_NEW_CONFIG_PASSWORD');
    expect(mockAskPassword).not.toHaveBeenCalled();
  });

  it('refuses a password below the portal floor', async () => {
    mockReadStdinValue.mockResolvedValue('short');
    await expect(mod.resolveNewPassword(true)).rejects.toThrow(
      String(mod.MIN_CONFIG_PASSWORD_LENGTH)
    );
  });
});

describe('changeConfigPassword', () => {
  it('logs in, elevates, writes the slot and verifies it with the new password', async () => {
    await mod.changeConfigPassword('eu-bench', NEW_PASSWORD);

    expect(state.pulls).toBe(1);
    expect(state.calls).toEqual([
      'POST /auth/login',
      'POST /auth/2fa/verify',
      'GET /auth/reauth/status',
      'POST /auth/reauth/totp',
      'PUT /configs/slots/password',
    ]);
    // The slot the server holds opens with the new password, through enable --password's own read.
    const slot = state.slot as { kdfParams: crypto.SlotKdfParams; wrappedCek: string };
    const secret = await crypto.derivePasswordSlotSecret(NEW_PASSWORD, slot.kdfParams);
    const back = await crypto.unwrapCekForSlot(
      slot.wrappedCek,
      secret,
      state.serverSecret as Uint8Array
    );
    expect(await crypto.exportAesKey(back)).toEqual(
      await crypto.exportAesKey(state.cek as CryptoKey)
    );
    expect(mockAccountServerFetch).toHaveBeenCalledWith(
      '/account/api/v1/configs/password-enroll',
      expect.objectContaining({ body: {} })
    );
    expect(said.at(-1)).toContain('eu-bench');
    expectNoSecret(allOutput());
  });

  it('omits configId from the verify when the local remote has no team', async () => {
    await mod
      .verifyNewPassword(API, { storeId: STORE_ID, configId: CONFIG_ID }, NEW_PASSWORD, {
        cek: state.cek as CryptoKey,
        serverSecret: state.serverSecret as Uint8Array,
      })
      .catch(() => undefined);
    expect(mockAccountServerFetch).toHaveBeenCalledWith(
      '/account/api/v1/configs/password-enroll',
      expect.objectContaining({ body: {} })
    );
  });

  it('names the config in the verify when the local remote has a team', async () => {
    await mod
      .verifyNewPassword(
        API,
        { storeId: STORE_ID, configId: CONFIG_ID, teamId: 'team-1' },
        NEW_PASSWORD,
        { cek: state.cek as CryptoKey, serverSecret: state.serverSecret as Uint8Array }
      )
      .catch(() => undefined);
    expect(mockAccountServerFetch).toHaveBeenCalledWith(
      '/account/api/v1/configs/password-enroll',
      expect.objectContaining({ body: { configId: CONFIG_ID } })
    );
  });

  it('skips the step-up while the account is already elevated', async () => {
    state.elevated = true;
    vi.stubEnv('REDIACC_LOGIN_TOTP_NEXT', '');
    await mod.changeConfigPassword('eu-bench', NEW_PASSWORD);
    expect(state.calls).not.toContain('POST /auth/reauth/totp');
    expect(state.slot).toBeDefined();
  });

  it('refuses without a step-up code, naming REDIACC_LOGIN_TOTP_NEXT, before any slot write', async () => {
    vi.stubEnv('REDIACC_LOGIN_TOTP_NEXT', '');
    const error = await mod.changeConfigPassword('eu-bench', NEW_PASSWORD).catch((e: Error) => e);
    expect((error as Error).message).toContain('REDIACC_LOGIN_TOTP_NEXT');
    expect(state.calls).not.toContain('PUT /configs/slots/password');
    expect(mockAskInput).not.toHaveBeenCalled();
  });

  it('refuses a step-up code that repeats the sign-in code (one use per step)', async () => {
    vi.stubEnv('REDIACC_LOGIN_TOTP_NEXT', LOGIN_TOTP);
    const error = await mod.changeConfigPassword('eu-bench', NEW_PASSWORD).catch((e: Error) => e);
    expect((error as Error).message).toContain('REDIACC_LOGIN_TOTP_NEXT');
    expect(state.calls).not.toContain('POST /auth/reauth/totp');
  });

  it('surfaces a refused step-up with its status and the server message', async () => {
    state.reauthStatus = 400;
    const error = await mod.changeConfigPassword('eu-bench', NEW_PASSWORD).catch((e: Error) => e);
    expect((error as Error).message).toContain('HTTP 400');
    expect((error as Error).message).toContain('Invalid verification code');
    expect(state.slot).toBeUndefined();
  });

  it('surfaces a server 403 on the slot write verbatim, with no secret', async () => {
    state.putStatus = 403;
    state.putError =
      'This config store requires a passkey; other unlock methods cannot be enrolled.';
    const error = await mod.changeConfigPassword('eu-bench', NEW_PASSWORD).catch((e: Error) => e);
    const message = (error as Error).message;
    expect(message).toContain('HTTP 403');
    expect(message).toContain('requires a passkey');
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
    expectNoSecret(`${message}\n${allOutput()}`);
  });

  it('reports a written slot that does not unlock with the new password', async () => {
    mockAccountServerFetch.mockResolvedValue({
      method: 'password',
      kdfParams: crypto.newPasswordSlotParams(),
      wrappedCek: 'AAAA',
      token: 't',
      storeId: STORE_ID,
      configId: CONFIG_ID,
      teamId: null,
    });
    const error = await mod.changeConfigPassword('eu-bench', NEW_PASSWORD).catch((e: Error) => e);
    expect((error as Error).message).toContain('was written');
    expectNoSecret((error as Error).message);
  });

  it('names the missing login field off a TTY', async () => {
    vi.stubEnv('REDIACC_LOGIN_PASSWORD', '');
    const error = await mod.changeConfigPassword('eu-bench', NEW_PASSWORD).catch((e: Error) => e);
    expect((error as Error).message).toContain('REDIACC_LOGIN_PASSWORD');
    expect(state.calls).toEqual([]);
  });
});

describe('command registration', () => {
  it('registers `remote password change` with no option that takes a password value', async () => {
    vi.doMock('../../services/config/config-resources.js', () => ({
      configService: { getEffectiveConfigName: () => 'rediacc' },
    }));
    const { registerRemoteCommands } = await import('../config-remote.js');
    const { Command } = await import('commander');
    const config = new Command('config');
    registerRemoteCommands(config);
    const change = config.commands
      .find((c) => c.name() === 'remote')
      ?.commands.find((c) => c.name() === 'password')
      ?.commands.find((c) => c.name() === 'change');
    expect(change).toBeDefined();
    expect(change?.options.map((o) => o.long)).toEqual(['--new-password-stdin']);
    expect(change?.options.filter((o) => o.required)).toEqual([]);
  });
});
