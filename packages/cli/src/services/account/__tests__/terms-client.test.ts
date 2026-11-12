/**
 * PLAN-terms-acceptance C2: how the account client treats the Terms refusal and notice. A 403
 * TERMS_ACCEPTANCE_REQUIRED becomes one validation-class line with the URL and never opens a
 * prompt; the `x-rediacc-terms` header is printed once per process on stderr and never refuses.
 */

import { type E2eRequestEnvelope, openRequest, sealResponse } from '@rediacc/shared/e2e';
import { LEGAL_URLS } from '@rediacc/shared/legal';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  askConfirm: vi.fn(),
  askChoice: vi.fn(),
  askInput: vi.fn(),
  stderr: vi.fn(),
}));

vi.mock('../../../utils/prompt.js', () => ({
  askConfirm: m.askConfirm,
  askChoice: m.askChoice,
  askInput: m.askInput,
}));
vi.mock('../../core/request-context.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../core/request-context.js')>()),
  writeStderr: m.stderr,
}));
vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));

import {
  type AccountFetchError,
  accountServerFetch,
  resetTermsNoticeForTests,
} from '../account-client.js';

/** A tunnel server that answers every request with the given inner status, body and outer headers. */
async function tunnel(status: number, body: unknown, headers: Record<string, string> = {}) {
  const pair = (await crypto.subtle.generateKey({ name: 'X25519' }, true, [
    'deriveBits',
  ])) as CryptoKeyPair;
  const calls = vi.fn();
  const fetchImpl = (async (_url: string, init: RequestInit) => {
    calls();
    const { aesKey } = await openRequest(
      pair.privateKey,
      JSON.parse(init.body as string) as E2eRequestEnvelope
    );
    const envelope = await sealResponse(aesKey, status, JSON.stringify(body));
    return new Response(JSON.stringify(envelope), { status: 200, headers });
  }) as unknown as typeof fetch;
  return { calls, fetchImpl, serverKey: { key: pair.publicKey, keyId: 'test-key' } };
}

const OPTIONS = { token: 'rdt_x', serverUrl: 'https://account.example.test' };

beforeEach(() => {
  vi.clearAllMocks();
  resetTermsNoticeForTests();
});

describe('403 TERMS_ACCEPTANCE_REQUIRED', () => {
  it('is one validation-class line with the URL, and no prompt is ever opened', async () => {
    const url = 'https://example.test/en/terms-of-service';
    const t = await tunnel(403, {
      error: 'Terms acceptance required',
      code: 'TERMS_ACCEPTANCE_REQUIRED',
      details: { version: '2026-11-11', sha256: 'a'.repeat(64), url },
    });
    const error = (await accountServerFetch('/account/api/v1/licenses/status', {
      ...OPTIONS,
      fetchImpl: t.fetchImpl,
      serverKey: t.serverKey,
    }).catch((e: unknown) => e)) as AccountFetchError;
    expect(error.name).toBe('ValidationError');
    expect(error.message).toContain('errors.terms.required');
    expect(error.message).toContain(url);
    expect(error.message).not.toContain('\n');
    expect(error.code).toBe('TERMS_ACCEPTANCE_REQUIRED');
    expect(error.status).toBe(403);
    expect(t.calls).toHaveBeenCalledTimes(1);
    expect(m.askConfirm).not.toHaveBeenCalled();
    expect(m.askChoice).not.toHaveBeenCalled();
    expect(m.askInput).not.toHaveBeenCalled();
  });

  it('prints both the accept page and the document when the server sends acceptUrl', async () => {
    const acceptUrl = 'https://account.example.test/account/terms';
    const t = await tunnel(403, {
      code: 'TERMS_ACCEPTANCE_REQUIRED',
      details: { url: 'https://example.test/t', acceptUrl },
    });
    const error = (await accountServerFetch('/x', {
      ...OPTIONS,
      fetchImpl: t.fetchImpl,
      serverKey: t.serverKey,
    }).catch((e: unknown) => e)) as Error;
    expect(error.message).toContain('errors.terms.requiredAccept');
    expect(error.message).toContain(acceptUrl);
    expect(error.message).toContain('https://example.test/t');
  });

  it('a FREE refusal names the flag and the env var next to the URL', async () => {
    const t = await tunnel(403, {
      code: 'TERMS_ACCEPTANCE_REQUIRED',
      details: { url: 'https://example.test/t', flag: '--accept-terms', env: 'RDC_ACCEPT_TERMS=1' },
    });
    const error = (await accountServerFetch('/account/api/v1/licenses/free', {
      method: 'POST',
      noAuth: true,
      serverUrl: OPTIONS.serverUrl,
      fetchImpl: t.fetchImpl,
      serverKey: t.serverKey,
    }).catch((e: unknown) => e)) as Error;
    expect(error.message).toContain('errors.terms.requiredFree');
    expect(error.message).toContain('--accept-terms');
    expect(error.message).toContain('RDC_ACCEPT_TERMS=1');
    expect(error.message).toContain('https://example.test/t');
  });

  it('names the Terms page when the refusal carries no url', async () => {
    const t = await tunnel(403, { code: 'TERMS_ACCEPTANCE_REQUIRED', details: {} });
    const error = (await accountServerFetch('/x', {
      ...OPTIONS,
      fetchImpl: t.fetchImpl,
      serverKey: t.serverKey,
    }).catch((e: unknown) => e)) as Error;
    expect(error.message).toContain(LEGAL_URLS.terms);
    expect(error.message).not.toContain('"url":""');
  });

  it('any other 403 keeps its own message', async () => {
    const t = await tunnel(403, { error: 'Forbidden for another reason', code: 'OTHER' });
    await expect(
      accountServerFetch('/x', { ...OPTIONS, fetchImpl: t.fetchImpl, serverKey: t.serverKey })
    ).rejects.toThrow('Forbidden for another reason');
  });
});

describe('x-rediacc-terms', () => {
  it('prints once per process on stderr and never refuses', async () => {
    const t = await tunnel(
      200,
      { ok: true },
      { 'x-rediacc-terms': 'upcoming=2027-01-01; effective=2027-02-01; url=https://example.test/t' }
    );
    const opts = { ...OPTIONS, fetchImpl: t.fetchImpl, serverKey: t.serverKey };
    await expect(accountServerFetch('/x', opts)).resolves.toEqual({ ok: true });
    await expect(accountServerFetch('/x', opts)).resolves.toEqual({ ok: true });
    expect(m.stderr).toHaveBeenCalledTimes(1);
    const line = m.stderr.mock.calls[0][0] as string;
    expect(line).toContain('errors.terms.upcoming');
    expect(line).toContain('2027-01-01');
    expect(line).toContain('2027-02-01');
    expect(line).toContain('https://example.test/t');
  });

  it('prints nothing when the header is absent', async () => {
    const t = await tunnel(200, { ok: true });
    await accountServerFetch('/x', { ...OPTIONS, fetchImpl: t.fetchImpl, serverKey: t.serverKey });
    expect(m.stderr).not.toHaveBeenCalled();
  });
});
