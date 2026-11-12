/**
 * An on-prem server that refused its cert at boot answers 503 DELEGATION_CERT_REFUSED; the account
 * client turns it into one translated validation-class line naming `rdc server licence`.
 */

import { type E2eRequestEnvelope, openRequest, sealResponse } from '@rediacc/shared/e2e';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));

import { type AccountFetchError, accountServerFetch } from '../account-client.js';

async function tunnel(status: number, body: unknown) {
  const pair = (await crypto.subtle.generateKey({ name: 'X25519' }, true, [
    'deriveBits',
  ])) as CryptoKeyPair;
  const fetchImpl = (async (_url: string, init: RequestInit) => {
    const { aesKey } = await openRequest(
      pair.privateKey,
      JSON.parse(init.body as string) as E2eRequestEnvelope
    );
    const envelope = await sealResponse(aesKey, status, JSON.stringify(body));
    return new Response(JSON.stringify(envelope), { status: 200 });
  }) as unknown as typeof fetch;
  return { fetchImpl, serverKey: { key: pair.publicKey, keyId: 'test-key' } };
}

const OPTIONS = { token: 'rdt_x', serverUrl: 'https://box.example.test' };

describe('503 DELEGATION_CERT_REFUSED', () => {
  it('is one validation-class line with its code, not the raw server text', async () => {
    const t = await tunnel(503, { error: 'raw server text', code: 'DELEGATION_CERT_REFUSED' });
    const error = (await accountServerFetch('/account/api/v1/licenses/free', {
      ...OPTIONS,
      ...t,
    }).catch((e: unknown) => e)) as AccountFetchError;
    expect(error.name).toBe('ValidationError');
    expect(error.message).toBe(
      `errors.delegationCertRefused ${JSON.stringify({ code: 'DELEGATION_CERT_REFUSED' })}`
    );
    expect(error.status).toBe(503);
    expect(error.code).toBe('DELEGATION_CERT_REFUSED');
  });

  it('any other 503 keeps its own message', async () => {
    const t = await tunnel(503, { error: 'Service unavailable', code: 'OTHER' });
    await expect(accountServerFetch('/x', { ...OPTIONS, ...t })).rejects.toMatchObject({
      message: 'Service unavailable',
      status: 503,
    });
  });
});
