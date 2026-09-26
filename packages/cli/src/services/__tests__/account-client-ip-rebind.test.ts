/**
 * The central TOKEN_IP_MISMATCH handling in accountServerFetch
 * (PLAN-token-ip-rebind.md, section 6.2).
 *
 * The tunnel crypto is mocked to pass values straight through, and fetch is a
 * scripted queue of INNER responses per path, so every round trip the client
 * makes is visible and a surplus one runs the queue dry (which fails loudly).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const STORED_TOKEN = 'rdc_stored_token';
const SERVER = 'https://eu.test';
const MISMATCH_MESSAGE = 'Token is bound to a different IP address';

const mockAskInput = vi.hoisted(() =>
  vi.fn<(message: string, pattern: RegExp) => Promise<string>>()
);
const spinnerState = vi.hoisted(() => ({ inside: false, promptedInside: [] as boolean[] }));
const mockSuspendSpinner = vi.hoisted(() =>
  vi.fn(async <T>(fn: () => Promise<T>): Promise<T> => {
    spinnerState.inside = true;
    try {
      return await fn();
    } finally {
      spinnerState.inside = false;
    }
  })
);
const mockWriteStderr = vi.hoisted(() => vi.fn());

vi.mock('@rediacc/shared/e2e', () => ({
  CURRENT_SERVER_E2E_KEY: { keyId: 'test', publicKeySpki: 'spki' },
  E2E_CONTENT_TYPE: 'application/x-test-e2e',
  importX25519PublicKey: vi.fn(() => Promise.resolve({})),
  // Pass-through: the "envelope" is the inner request itself, readable by the fetch stub.
  sealRequest: vi.fn(
    (
      _key: unknown,
      _keyId: string,
      method: string,
      path: string,
      headers: Record<string, string>,
      body: unknown
    ) => Promise.resolve({ envelope: { method, path, headers, body }, aesKey: 'aes' })
  ),
  openResponse: vi.fn((_aes: unknown, env: { status: number; body: string }) =>
    Promise.resolve(env)
  ),
}));

vi.mock('../account/subscription-auth.js', () => ({
  normalizeServerUrl: (url: string) => url.replace(/\/+$/, ''),
  getSubscriptionServerUrl: () => SERVER,
  getSubscriptionTokenState: () => ({
    kind: 'ready',
    serverUrl: SERVER,
    token: { token: STORED_TOKEN },
  }),
}));
vi.mock('../account/account-pointer.js', () => ({
  readAccountPointer: () => ({ e2ePublicKey: 'spki' }),
}));
vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: { update: vi.fn() },
}));
vi.mock('../config/config-name.js', () => ({ getEffectiveConfigName: () => 'rediacc' }));
vi.mock('../update/updater.js', () => ({ resolveChannel: () => 'stable' }));
vi.mock('../../version.js', () => ({ VERSION: '0.9.0' }));
vi.mock('../../utils/prompt.js', () => ({
  askInput: (message: string, pattern: RegExp) => {
    spinnerState.promptedInside.push(spinnerState.inside);
    return mockAskInput(message, pattern);
  },
}));
vi.mock('../../utils/spinner.js', () => ({ suspendSpinner: mockSuspendSpinner }));
vi.mock('../core/request-context.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../core/request-context.js')>()),
  writeStderr: mockWriteStderr,
}));

import { API_TOKEN_IP_REBIND_PATH } from '@rediacc/shared/subscription/types';
import { accountServerFetch } from '../account/account-client.js';
import { resetTokenIpRebindState } from '../account/token-ip-rebind.js';

interface InnerRequest {
  method: string;
  path: string;
  headers: Record<string, string>;
  body: unknown;
}
interface InnerResponse {
  status: number;
  body: Record<string, unknown>;
}

const DATA_PATH = '/account/api/v1/licenses/status';
let script: Map<string, InnerResponse[]>;
let sent: InnerRequest[];

function queue(path: string, ...responses: InnerResponse[]): void {
  script.set(path, [...(script.get(path) ?? []), ...responses]);
}

const mismatch = (rebind: 'totp' | 'relogin' = 'totp'): InnerResponse => ({
  status: 403,
  body: { error: MISMATCH_MESSAGE, code: 'TOKEN_IP_MISMATCH', rebind },
});
const moved = (ip = '203.0.113.9'): InnerResponse => ({
  status: 200,
  body: { rebound: true, boundIp: ip },
});
const ok = (value: string): InnerResponse => ({ status: 200, body: { value } });
const wrongCode = (attemptsRemaining: number): InnerResponse => ({
  status: 400,
  body: { error: 'Invalid authentication code', code: 'TOTP_INVALID', attemptsRemaining },
});

function setTty(stdin: boolean, stderr: boolean): void {
  Object.defineProperty(process.stdin, 'isTTY', { value: stdin, configurable: true });
  Object.defineProperty(process.stderr, 'isTTY', { value: stderr, configurable: true });
}

const rebindCalls = () => sent.filter((r) => r.path === API_TOKEN_IP_REBIND_PATH);
const stderrText = () => mockWriteStderr.mock.calls.map((c) => String(c[0])).join('');

describe('accountServerFetch TOKEN_IP_MISMATCH rebind', () => {
  const originalFetch = globalThis.fetch;
  const originalStdinTty = process.stdin.isTTY;
  const originalStderrTty = process.stderr.isTTY;

  beforeEach(() => {
    vi.clearAllMocks();
    resetTokenIpRebindState();
    script = new Map();
    sent = [];
    spinnerState.inside = false;
    spinnerState.promptedInside = [];
    mockAskInput.mockResolvedValue('123456');
    setTty(true, true);
    globalThis.fetch = vi.fn((_url: string | URL | Request, init?: RequestInit) => {
      const inner = JSON.parse(String(init?.body)) as InnerRequest;
      sent.push(inner);
      const next = script.get(inner.path)?.shift();
      if (!next) {
        return Promise.reject(new Error(`fetch script ran dry for ${inner.method} ${inner.path}`));
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ status: next.status, body: JSON.stringify(next.body) }),
      } as unknown as Response);
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    Object.defineProperty(process.stdin, 'isTTY', { value: originalStdinTty, configurable: true });
    Object.defineProperty(process.stderr, 'isTTY', {
      value: originalStderrTty,
      configurable: true,
    });
  });

  it('TTY: prompts once, moves the token with the same bearer, and replays the request', async () => {
    queue(DATA_PATH, mismatch(), ok('after'));
    queue(API_TOKEN_IP_REBIND_PATH, moved('203.0.113.9'));

    const result = await accountServerFetch<{ value: string }>(DATA_PATH, {
      method: 'POST',
      body: { a: 1 },
    });

    expect(result).toEqual({ value: 'after' });
    expect(sent).toHaveLength(3);
    expect(mockAskInput).toHaveBeenCalledTimes(1);
    const [refused, rebind, retry] = sent;
    expect(rebind).toMatchObject({
      method: 'POST',
      path: API_TOKEN_IP_REBIND_PATH,
      body: { code: '123456' },
    });
    expect(rebind.headers.Authorization).toBe(`Bearer ${STORED_TOKEN}`);
    expect(refused.headers.Authorization).toBe(`Bearer ${STORED_TOKEN}`);
    expect(retry).toEqual(refused);
    expect(stderrText()).toContain('203.0.113.9');
  });

  it('retries exactly once: a second mismatch after a move is reported, not prompted again', async () => {
    queue(DATA_PATH, mismatch(), mismatch());
    queue(API_TOKEN_IP_REBIND_PATH, moved());

    const failure = await accountServerFetch(DATA_PATH).catch((e: unknown) => e);

    expect((failure as Error).message).toMatch(/still sees a different IP address/);
    expect(failure).toMatchObject({ status: 403, code: 'TOKEN_IP_MISMATCH' });
    expect(mockAskInput).toHaveBeenCalledTimes(1);
    expect(sent).toHaveLength(3);
  });

  it('non-TTY: no prompt, one fetch, both remedies named, status and code kept', async () => {
    setTty(false, true);
    queue(DATA_PATH, mismatch());

    const failure = await accountServerFetch(DATA_PATH).catch((e: unknown) => e);

    expect(mockAskInput).not.toHaveBeenCalled();
    expect(sent).toHaveLength(1);
    const message = (failure as Error).message;
    expect(message).toContain('rdc subscription status');
    expect(message).toContain('rdc subscription login');
    expect(failure).toMatchObject({ status: 403, code: 'TOKEN_IP_MISMATCH' });
  });

  it('non-TTY stderr alone is enough to refuse the prompt', async () => {
    setTty(true, false);
    queue(DATA_PATH, mismatch());

    await expect(accountServerFetch(DATA_PATH)).rejects.toThrow(/interactive terminal/);
    expect(mockAskInput).not.toHaveBeenCalled();
  });

  it("rebind: 'relogin' on a TTY never prompts and says to log in again", async () => {
    queue(DATA_PATH, mismatch('relogin'));

    const failure = await accountServerFetch(DATA_PATH).catch((e: unknown) => e);

    expect(mockAskInput).not.toHaveBeenCalled();
    expect(sent).toHaveLength(1);
    expect((failure as Error).message).toMatch(/Two-factor authentication is off/);
    expect((failure as Error).message).toContain('rdc subscription login');
    expect(failure).toMatchObject({ status: 403, code: 'TOKEN_IP_MISMATCH' });
  });

  it('a wrong code, then the right one: two prompts and one success', async () => {
    mockAskInput.mockResolvedValueOnce('000000').mockResolvedValueOnce('123456');
    queue(DATA_PATH, mismatch(), ok('after'));
    queue(API_TOKEN_IP_REBIND_PATH, wrongCode(4), moved());

    await expect(accountServerFetch(DATA_PATH)).resolves.toEqual({ value: 'after' });

    expect(mockAskInput).toHaveBeenCalledTimes(2);
    expect(rebindCalls().map((r) => r.body)).toEqual([{ code: '000000' }, { code: '123456' }]);
    expect(stderrText()).toContain('4 tries left');
  });

  it('gives up after three wrong codes', async () => {
    queue(DATA_PATH, mismatch());
    queue(API_TOKEN_IP_REBIND_PATH, wrongCode(4), wrongCode(3), wrongCode(2));

    const failure = await accountServerFetch(DATA_PATH).catch((e: unknown) => e);

    expect((failure as Error).message).toMatch(/Three wrong codes/);
    expect(mockAskInput).toHaveBeenCalledTimes(3);
    expect(sent).toHaveLength(4);
  });

  it('a reused code says to wait for the next one and asks again', async () => {
    queue(DATA_PATH, mismatch(), ok('after'));
    queue(
      API_TOKEN_IP_REBIND_PATH,
      { status: 409, body: { error: 'already used', code: 'TOTP_REPLAYED', attemptsRemaining: 4 } },
      moved()
    );

    await expect(accountServerFetch(DATA_PATH)).resolves.toEqual({ value: 'after' });
    expect(mockAskInput).toHaveBeenCalledTimes(2);
    expect(stderrText()).toMatch(/already used\. Wait for the next code/);
  });

  it('locked: the message carries the minutes and there is no further prompt', async () => {
    queue(DATA_PATH, mismatch());
    queue(API_TOKEN_IP_REBIND_PATH, {
      status: 429,
      body: { error: 'locked', code: 'IP_REBIND_LOCKED', retryAfter: 290 },
    });

    const failure = await accountServerFetch(DATA_PATH).catch((e: unknown) => e);

    expect((failure as Error).message).toMatch(/locked for 5 min/);
    expect(failure).toMatchObject({
      status: 403,
      code: 'TOKEN_IP_MISMATCH',
      details: { rebindCode: 'IP_REBIND_LOCKED', retryAfter: 290 },
    });
    expect(mockAskInput).toHaveBeenCalledTimes(1);
  });

  it('disabled (403 IP_REBIND_DISABLED) is final', async () => {
    queue(DATA_PATH, mismatch());
    queue(API_TOKEN_IP_REBIND_PATH, {
      status: 403,
      body: { error: 'disabled', code: 'IP_REBIND_DISABLED' },
    });

    await expect(accountServerFetch(DATA_PATH)).rejects.toThrow(/turned off for this token/);
    expect(mockAskInput).toHaveBeenCalledTimes(1);
  });

  it('a failed outcome is cached: a later mismatch in the same process fails without prompting', async () => {
    setTty(false, false);
    queue(DATA_PATH, mismatch(), mismatch());

    await expect(accountServerFetch(DATA_PATH)).rejects.toThrow(/interactive terminal/);
    setTty(true, true);
    await expect(accountServerFetch(DATA_PATH)).rejects.toThrow(/interactive terminal/);
    expect(mockAskInput).not.toHaveBeenCalled();
  });

  it('concurrency: two parallel calls share one prompt and one rebind, and both are retried', async () => {
    queue(DATA_PATH, mismatch(), mismatch(), ok('one'), ok('two'));
    queue(API_TOKEN_IP_REBIND_PATH, moved());

    const results = await Promise.all([
      accountServerFetch<{ value: string }>(DATA_PATH),
      accountServerFetch<{ value: string }>(DATA_PATH),
    ]);

    expect(results.map((r) => r.value).sort()).toEqual(['one', 'two']);
    expect(mockAskInput).toHaveBeenCalledTimes(1);
    expect(rebindCalls()).toHaveLength(1);
    expect(sent).toHaveLength(5);
  });

  it('ipRebind: false opts out: no prompt, the server error as is', async () => {
    queue(DATA_PATH, mismatch());

    const failure = await accountServerFetch(DATA_PATH, { ipRebind: false }).catch(
      (e: unknown) => e
    );

    expect((failure as Error).message).toBe(MISMATCH_MESSAGE);
    expect(mockAskInput).not.toHaveBeenCalled();
    expect(sent).toHaveLength(1);
  });

  it('noAuth never triggers the rebind path', async () => {
    queue(DATA_PATH, mismatch());

    await expect(accountServerFetch(DATA_PATH, { noAuth: true })).rejects.toThrow(MISMATCH_MESSAGE);
    expect(mockAskInput).not.toHaveBeenCalled();
    expect(sent[0].headers.Authorization).toBeUndefined();
  });

  it('an explicit options.token is the token the rebind and the retry carry', async () => {
    queue(DATA_PATH, mismatch(), ok('after'));
    queue(API_TOKEN_IP_REBIND_PATH, moved());

    await accountServerFetch(DATA_PATH, { token: 'rdc_explicit' });

    expect(sent.map((r) => r.headers.Authorization)).toEqual([
      'Bearer rdc_explicit',
      'Bearer rdc_explicit',
      'Bearer rdc_explicit',
    ]);
  });

  it('the prompt runs inside suspendSpinner', async () => {
    queue(DATA_PATH, mismatch(), ok('after'));
    queue(API_TOKEN_IP_REBIND_PATH, moved());

    await accountServerFetch(DATA_PATH);

    expect(mockSuspendSpinner).toHaveBeenCalledTimes(1);
    expect(spinnerState.promptedInside).toEqual([true]);
  });
});
