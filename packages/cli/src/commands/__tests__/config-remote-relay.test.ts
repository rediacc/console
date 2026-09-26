/**
 * The server relay is the only way config keys reach the CLI (PLAN-config-handoff-relay-only.md, section 7.1).
 *
 * Real X25519 crypto and the real shared fingerprint functions; only the I/O seams are mocked: the account
 * API (accountServerFetch), output, the browser launch, and, for the command-level cases, the store/finalize
 * step (applyHandoff) and the prompts.
 */

import { createHash } from 'node:crypto';
import {
  cekHandoffEncrypt,
  fromBase64,
  handoffKeyHash,
  handoffPairingCode,
  handoffPollVerifier,
} from '@rediacc/shared/config-crypto';
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ValidationError } from '../../utils/errors.js';
import { generateX25519KeyPair, type HandoffPayload } from '../config-remote-handoff.js';

const API = 'https://acct.example.com';
const CREATE = '/account/api/v1/device-codes';
const DEVICE_CODE = '0f1e2d3c-4b5a-4968-8776-a5b4c3d2e1f0';
const CLAIM = `${CREATE}/${DEVICE_CODE}/claim`;
const CANCEL = `${CREATE}/${DEVICE_CODE}`;

const {
  mockFetch,
  lines,
  warnings,
  errors,
  mockExecFile,
  mockApply,
  mockStore,
  mockConfirm,
  loaded,
} = vi.hoisted(() => ({
  mockFetch: vi.fn(),
  lines: [] as string[],
  warnings: [] as string[],
  errors: [] as unknown[],
  mockExecFile: vi.fn(),
  mockApply: vi.fn(),
  mockStore: vi.fn(),
  mockConfirm: vi.fn(),
  loaded: { remote: undefined as unknown },
}));

vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: mockFetch }));

vi.mock('../../services/core/output.js', () => {
  const push = (m: string) => {
    lines.push(m);
  };
  return {
    outputService: {
      info: push,
      success: push,
      print: push,
      error: push,
      warn: (m: string) => {
        warnings.push(m);
      },
    },
  };
});

vi.mock('node:child_process', () => ({ execFile: mockExecFile }));

vi.mock('../config-remote-enable.js', () => ({
  checkEnablePrerequisites: vi.fn(() =>
    Promise.resolve({ token: 'rdt_login', email: 'op@example.com' })
  ),
  requireLoginToken: vi.fn(() => 'rdt_login'),
  applyHandoff: mockApply,
  storeHandoffCredentials: mockStore,
}));

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: {
    load: vi.fn(() => Promise.resolve({ schemaVersion: 3, id: 'cfg', remote: loaded.remote })),
  },
}));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getEffectiveConfigName: () => 'test' },
}));

vi.mock('../../services/account/subscription-auth.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/account/subscription-auth.js')>()),
  getSubscriptionServerUrl: () => API,
}));

vi.mock('../../utils/prompt.js', () => ({ askConfirm: mockConfirm }));

vi.mock('../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/errors.js')>()),
  handleError: (e: unknown) => {
    errors.push(e);
  },
}));

const relay = await import('../config-remote-relay.js');
const { registerRemoteCommands, rotateCek } = await import('../config-remote.js');

// ─── helpers ──────────────────────────────────────────────────────────────

interface Created {
  body: { purpose: string; keyHash: string; pollVerifier: string };
  token?: string;
}

/** What the fake server saw at create time, and the pieces the printed link carried. */
function created(): Created {
  const call = mockFetch.mock.calls.find(
    ([path, opts]) => path === CREATE && opts?.method === 'POST'
  );
  if (!call) throw new Error('no create call');
  return call[1] as Created;
}

function printedUrl(): URL {
  const line = lines.find((l) => l.includes('/account/config-remote'));
  if (!line) throw new Error('no link printed');
  return new URL(line.trim());
}

function fragment(): URLSearchParams {
  return new URLSearchParams(printedUrl().hash.slice(1));
}

async function sealFor(payload: Partial<HandoffPayload>, spkiB64?: string): Promise<string> {
  const keyB64 = spkiB64 ?? (fragment().get('key') as string);
  const spki = fromBase64(keyB64);
  const pub = await crypto.subtle.importKey(
    'spki',
    spki.buffer.slice(spki.byteOffset, spki.byteOffset + spki.byteLength) as ArrayBuffer,
    { name: 'X25519' },
    false,
    []
  );
  const blob = await cekHandoffEncrypt(new TextEncoder().encode(JSON.stringify(payload)), pub);
  return JSON.stringify(blob);
}

const PAYLOAD_BASE = {
  passkey_secret: 'cGFzc2tleV9zZWNyZXRfMzJfYnl0ZXNfYjY0',
  token: 'rct_rotated_latest',
  storageKeyId: 'rdc:pk:55555555-5555-4555-8555-555555555555',
  wrappedCek: 'd3JhcHBlZF9jZWtfb3BhcXVl',
  storeId: '11111111-1111-4111-8111-111111111111',
  apiUrl: API,
};

type ClaimAnswer = (n: number) => Promise<unknown>;

/** Route the fake account server: create answers with the code, claim/cancel follow `claim`. */
function server(
  claim: ClaimAnswer,
  cancel: (opts: { body?: unknown }) => Promise<unknown> = () => Promise.resolve({})
) {
  let claims = 0;
  mockFetch.mockImplementation((path: string, opts?: { method?: string; body?: unknown }) => {
    if (path === CREATE && opts?.method === 'POST') {
      return Promise.resolve({
        deviceCode: DEVICE_CODE,
        interval: 5,
        expiresIn: 600,
        expiresAt: new Date(Date.now() + 600_000).toISOString(),
      });
    }
    if (path === CLAIM) return claim(++claims);
    if (path === CANCEL && opts?.method === 'DELETE') return cancel(opts);
    return Promise.reject(new Error(`unexpected ${opts?.method ?? 'GET'} ${path}`));
  });
}

const httpError = (status: number, extra: Record<string, unknown> = {}) =>
  Object.assign(new Error(`HTTP ${status}`), { status, ...extra });

/** One real event-loop turn (setImmediate is not faked). */
const realTurn = () => new Promise<void>((resolve) => setImmediate(resolve));

/**
 * Settle `p`, moving the fake clock only while the code under test waits on a fake timer.
 *
 * Key generation, sealing and opening a handoff are real WebCrypto work on the libuv threadpool,
 * outside the fake clock. The old loop advanced the clock by a fixed step on every iteration, so
 * under CPU contention the clock ran past the code's `expiresAt` (or the step budget ran out) while
 * that work was still in flight: "Device code expired" and 30 s timeouts, 14 of 30 runs red on a
 * loaded machine. Now a pending timer means the code is idle, and the clock moves by `stepMs`; no
 * pending timer means real work is in flight, and a real turn passes instead. The outcome depends
 * on the order of events only, never on how fast the machine is.
 */
async function drive<T>(p: Promise<T>, stepMs = 1000): Promise<T> {
  let done = false;
  const tracked = p.finally(() => {
    done = true;
  });
  tracked.catch(() => {});
  while (!done) {
    if (vi.getTimerCount() > 0) await vi.advanceTimersByTimeAsync(stepMs);
    else await realTurn();
  }
  return tracked;
}

async function runEnable() {
  const program = new Command();
  program.exitOverride();
  registerRemoteCommands(program.command('config'));
  await program.parseAsync(['node', 'rdc', 'config', 'remote', 'enable']);
}

const errorText = () => errors.map((e) => (e instanceof Error ? e.message : String(e))).join('\n');

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
  lines.length = 0;
  warnings.length = 0;
  errors.length = 0;
  mockFetch.mockReset();
  mockExecFile.mockReset();
  mockApply.mockReset();
  mockStore.mockReset();
  mockConfirm.mockReset();
  loaded.remote = undefined;
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// ─── link and create ──────────────────────────────────────────────────────

describe('relay link', () => {
  it('carries code, key and nonce in the fragment only: no query, no callback, no loopback', () => {
    const url = relay.relayUrl(`${API}/`, DEVICE_CODE, 'cHVi+/=', 'bm9uY2U');
    expect(url).not.toContain('?');
    expect(url).not.toContain('callback');
    expect(url).not.toMatch(/localhost|127\.0\.0\.1/);
    const parsed = new URL(url);
    expect(parsed.origin + parsed.pathname).toBe(`${API}/account/config-remote`);
    const frag = new URLSearchParams(parsed.hash.slice(1));
    expect(frag.get('code')).toBe(DEVICE_CODE);
    // Percent-encoded, so `+` survives URLSearchParams parsing on the page.
    expect(frag.get('key')).toBe('cHVi+/=');
    expect(frag.get('nonce')).toBe('bm9uY2U');
  });

  it('create sends the login token, the purpose, H(spki) and H(pollSecret)', async () => {
    server(() => Promise.reject(httpError(404)));
    const handle = await relay.startRelayHandoff(API, 'rdt_login');

    const { body, token } = created();
    expect(token).toBe('rdt_login');
    expect(body.purpose).toBe('config-handoff');
    const spki = fromBase64(
      new URLSearchParams(new URL(handle.url).hash.slice(1)).get('key') as string
    );
    expect(body.keyHash).toBe(await handoffKeyHash(spki));
    // The server hashes the RAW 32 secret bytes, not the base64url text (device-code.service.ts pollVerifierOf).
    const raw = Buffer.from(handle.pollSecret, 'base64url');
    expect(handle.pollSecret).toMatch(/^[\w-]{43}$/);
    expect(raw).toHaveLength(32);
    expect(body.pollVerifier).toBe(await handoffPollVerifier(raw));
    expect(body.pollVerifier).toBe(createHash('sha256').update(raw).digest('base64url'));
    expect(body.pollVerifier).not.toBe(
      createHash('sha256').update(handle.pollSecret, 'utf8').digest('base64url')
    );
    // The secret itself never goes to the create call.
    expect(JSON.stringify(body)).not.toContain(handle.pollSecret);
    expect(handle.nonce).toMatch(/^[\w-]{43}$/);
    expect(handle.expiresAt).toBeGreaterThan(Date.now());
  });
});

// ─── the whole enable over the relay ──────────────────────────────────────

describe('config remote enable over the relay', () => {
  it('prints the pairing code derived from the link key', async () => {
    server(() => Promise.reject(httpError(404)));
    await drive(runEnable());

    const key = fragment().get('key') as string;
    const code = await handoffPairingCode(fromBase64(key));
    const pairingLine = lines.find((l) => l.startsWith('Pairing code'));
    expect(pairingLine).toBeDefined();
    expect(pairingLine).toContain(code);
    expect(lines.some((l) => l.includes('signed in as op@example.com'))).toBe(true);
    expect(lines.some((l) => l.includes('Press Ctrl+C to cancel'))).toBe(true);
  });

  it('creates the code first, claims pending then complete, and applies the handoff once', async () => {
    server(async (n) => {
      if (n < 3) return { status: 'pending' };
      return {
        status: 'complete',
        configHandoff: await sealFor({
          ...PAYLOAD_BASE,
          handoffNonce: fragment().get('nonce') as string,
        }),
      };
    });

    await drive(runEnable());

    expect(errorText()).toBe('');
    const order = mockFetch.mock.calls.map(([path]) => path);
    expect(order[0]).toBe(CREATE);
    expect(order.slice(1)).toEqual([CLAIM, CLAIM, CLAIM]);
    const claimBody = mockFetch.mock.calls[1][1] as {
      body: { pollSecret: string };
      noAuth: boolean;
    };
    expect(claimBody.noAuth).toBe(true);
    expect(await handoffPollVerifier(Buffer.from(claimBody.body.pollSecret, 'base64url'))).toBe(
      created().body.pollVerifier
    );
    expect(mockApply).toHaveBeenCalledTimes(1);
    expect(mockApply.mock.calls[0][0]).toMatchObject({ storeId: PAYLOAD_BASE.storeId });
  });

  it("a nonce that is not this run's refuses and writes nothing", async () => {
    server(async () => ({
      status: 'complete',
      configHandoff: await sealFor({
        ...PAYLOAD_BASE,
        handoffNonce: 'bm90X3RoaXNfcnVuc19ub25jZV9hdF9hbGxfeHh4eHh4eA',
      }),
    }));

    await drive(runEnable());

    expect(errors).toHaveLength(1);
    expect(errors[0]).toBeInstanceOf(ValidationError);
    expect(errorText()).toContain('not issued for this run');
    expect(mockApply).not.toHaveBeenCalled();
    expect(mockStore).not.toHaveBeenCalled();
  });

  it('a handoff without a nonce refuses too', async () => {
    server(async () => ({ status: 'complete', configHandoff: await sealFor({ ...PAYLOAD_BASE }) }));

    await drive(runEnable());

    expect(errorText()).toContain('not issued for this run');
    expect(mockApply).not.toHaveBeenCalled();
  });

  it('a blob sealed to another key raises handoffUndecryptable', async () => {
    const other = await generateX25519KeyPair();
    const otherSpki = new Uint8Array(await crypto.subtle.exportKey('spki', other.publicKey));
    server(async () => ({
      status: 'complete',
      configHandoff: await sealFor(
        { ...PAYLOAD_BASE, handoffNonce: fragment().get('nonce') as string },
        Buffer.from(otherSpki).toString('base64')
      ),
    }));

    await drive(runEnable());

    expect(errors[0]).toBeInstanceOf(ValidationError);
    expect(errorText()).toMatch(/cannot open/);
    expect(mockApply).not.toHaveBeenCalled();
  });
});

// ─── the claim loop ───────────────────────────────────────────────────────

describe('claim loop', () => {
  function started() {
    return relay.startRelayHandoff(API, 'rdt_login');
  }

  it('a 429 waits for Retry-After before the next claim', async () => {
    const times: number[] = [];
    server(async (n) => {
      times.push(Date.now());
      if (n === 1) throw httpError(429, { retryAfter: 12 });
      return {
        status: 'complete',
        configHandoff: await sealFor({ ...PAYLOAD_BASE, handoffNonce: handle.nonce }, key),
      };
    });
    const handle = await started();
    const key = new URLSearchParams(new URL(handle.url).hash.slice(1)).get('key') as string;

    await drive(relay.waitForRelayHandoff(API, handle), 500);

    expect(times).toHaveLength(2);
    expect(times[1] - times[0]).toBeGreaterThanOrEqual(12_000);
    expect(times[1] - times[0]).toBeLessThan(13_000);
  });

  it('a 429 without Retry-After backs off to the ceiling', async () => {
    const times: number[] = [];
    server((n) => {
      times.push(Date.now());
      return Promise.reject(httpError(n === 1 ? 429 : 404));
    });
    const handle = await started();

    await expect(drive(relay.waitForRelayHandoff(API, handle), 500)).rejects.toThrow(
      ValidationError
    );
    expect(times[1] - times[0]).toBeGreaterThanOrEqual(relay.MAX_BACKOFF_MS);
  });

  it('three network failures print one warning, then the claim recovers', async () => {
    server(async (n) => {
      if (n <= 4) throw new TypeError('fetch failed');
      return {
        status: 'complete',
        configHandoff: await sealFor({ ...PAYLOAD_BASE, handoffNonce: handle.nonce }, key),
      };
    });
    const handle = await started();
    const key = new URLSearchParams(new URL(handle.url).hash.slice(1)).get('key') as string;

    const payload = await drive(relay.waitForRelayHandoff(API, handle));

    expect(payload.storeId).toBe(PAYLOAD_BASE.storeId);
    const retrying = warnings.filter(
      (w) => w.includes('still retrying') || w.includes('Still retrying')
    );
    expect(retrying).toHaveLength(1);
    expect(retrying[0]).toContain(API);
  });

  it('5xx backs off exponentially and never past the ceiling', async () => {
    const times: number[] = [];
    server(() => {
      times.push(Date.now());
      return Promise.reject(httpError(times.length >= 6 ? 404 : 503));
    });
    const handle = await started();

    await expect(drive(relay.waitForRelayHandoff(API, handle), 500)).rejects.toThrow(
      ValidationError
    );
    const gaps = times.slice(1).map((t, i) => t - times[i]);
    expect(gaps[0]).toBeGreaterThanOrEqual(10_000);
    expect(gaps[1]).toBeGreaterThanOrEqual(20_000);
    for (const gap of gaps) expect(gap).toBeLessThanOrEqual(relay.MAX_BACKOFF_MS + 500);
  });

  it('expired (404) raises a ValidationError', async () => {
    server(() => Promise.reject(httpError(404, { message: 'expired' })));
    const handle = await started();

    await expect(drive(relay.waitForRelayHandoff(API, handle))).rejects.toThrow(/expired/i);
  });

  it('an {status:"expired"} body raises a ValidationError', async () => {
    server(() => Promise.resolve({ status: 'expired' }));
    const handle = await started();

    await expect(drive(relay.waitForRelayHandoff(API, handle))).rejects.toBeInstanceOf(
      ValidationError
    );
  });

  it('any other 4xx raises at once with the status', async () => {
    server(() => Promise.reject(httpError(403)));
    const handle = await started();

    await expect(drive(relay.waitForRelayHandoff(API, handle))).rejects.toThrow(/HTTP 403/);
    expect(mockFetch.mock.calls.filter(([p]) => p === CLAIM)).toHaveLength(1);
  });

  it('stops at the server expiresAt, not after a fixed number of attempts', async () => {
    server(() => Promise.resolve({ status: 'pending' }));
    const handle = await started();
    const start = Date.now();

    await expect(drive(relay.waitForRelayHandoff(API, handle), 5000)).rejects.toThrow(/expired/i);
    expect(Date.now() - start).toBeGreaterThanOrEqual(600_000);
    expect(Date.now() - start).toBeLessThan(610_000);
  });
});

// ─── Ctrl+C ───────────────────────────────────────────────────────────────

/**
 * Fire only the listeners added since `before`: vitest's worker has its own SIGINT handler, which kills the run.
 * The relay registers its listener after key generation, which settles on real event-loop turns outside the
 * fake clock, so this waits for the listener itself rather than for a fixed number of turns (1000 turns were
 * too few on a loaded machine: "expected [] to have a length of 1"). A listener that never comes is the
 * test's own timeout.
 */
async function ctrlC(before: Function[]) {
  const added = () => process.listeners('SIGINT').filter((l) => !before.includes(l));
  while (added().length === 0) await realTurn();
  expect(added()).toHaveLength(1);
  for (const listener of added()) (listener as () => void)();
}

describe('Ctrl+C during the wait', () => {
  it('sends DELETE with the poll secret, then exits 130', async () => {
    let cancelBody: unknown;
    server(
      () => Promise.resolve({ status: 'pending' }),
      (opts) => {
        cancelBody = opts.body;
        return Promise.resolve({});
      }
    );
    const exit = vi.spyOn(process, 'exit').mockImplementation((() => undefined) as never);

    const before = process.listeners('SIGINT');
    const run = relay.runRelayHandoff(API, 'rdt_login', 'op@example.com');
    run.catch(() => {});
    await vi.advanceTimersByTimeAsync(6000);
    await ctrlC(before);
    await vi.advanceTimersByTimeAsync(10);

    expect(cancelBody).toBeDefined();
    const { pollSecret } = cancelBody as { pollSecret: string };
    expect(await handoffPollVerifier(Buffer.from(pollSecret, 'base64url'))).toBe(
      created().body.pollVerifier
    );
    expect(exit).toHaveBeenCalledWith(130);
    expect(warnings.some((w) => w.startsWith('Cancelled'))).toBe(true);
    // Let the (still running, since exit is mocked) loop end.
    mockFetch.mockImplementation(() => Promise.reject(httpError(404)));
    await drive(run).catch(() => {});
  });

  it('a hanging DELETE does not hold the exit past two seconds', async () => {
    server(
      () => Promise.resolve({ status: 'pending' }),
      () => new Promise(() => {})
    );
    const exit = vi.spyOn(process, 'exit').mockImplementation((() => undefined) as never);

    const before = process.listeners('SIGINT');
    const run = relay.runRelayHandoff(API, 'rdt_login', undefined);
    run.catch(() => {});
    await vi.advanceTimersByTimeAsync(1000);
    await ctrlC(before);
    await vi.advanceTimersByTimeAsync(1900);
    expect(exit).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(200);
    expect(exit).toHaveBeenCalledWith(130);
    mockFetch.mockImplementation(() => Promise.reject(httpError(404)));
    await drive(run).catch(() => {});
  });

  it('removes its SIGINT listener once the wait ends', async () => {
    server(() => Promise.reject(httpError(404)));
    const before = process.listenerCount('SIGINT');
    await drive(relay.runRelayHandoff(API, 'rdt_login', undefined)).catch(() => {});
    expect(process.listenerCount('SIGINT')).toBe(before);
  });
});

// ─── rotate-cek ───────────────────────────────────────────────────────────

describe('config rotate-cek', () => {
  it('re-links over the relay helpers, not a loopback server', async () => {
    loaded.remote = { apiUrl: API, storeId: 's', configId: 'c', storageKeyId: 'k' };
    mockConfirm.mockResolvedValue(true);
    server(async () => ({
      status: 'complete',
      configHandoff: await sealFor({
        ...PAYLOAD_BASE,
        handoffNonce: 'wrong-nonce-so-the-run-stops-before-store',
      }),
    }));

    await expect(drive(rotateCek('test', API))).rejects.toThrow(/not issued for this run/);

    expect(created().body.purpose).toBe('config-handoff');
    expect(created().token).toBe('rdt_login');
    expect(fragment().get('code')).toBe(DEVICE_CODE);
    expect(mockFetch.mock.calls.some(([p]) => p === CLAIM)).toBe(true);
    expect(mockStore).not.toHaveBeenCalled();
  });
});

// ─── the loopback is gone ─────────────────────────────────────────────────

describe('no loopback transport', () => {
  it('the config-remote modules import no HTTP server', async () => {
    const { readFileSync } = await import('node:fs');
    const { fileURLToPath } = await import('node:url');
    for (const rel of [
      '../config-remote.ts',
      '../config-remote-relay.ts',
      '../config-remote-enable.ts',
    ]) {
      const src = readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');
      expect(src, rel).not.toMatch(/node:http|createServer|callback=/);
    }
  });
});
