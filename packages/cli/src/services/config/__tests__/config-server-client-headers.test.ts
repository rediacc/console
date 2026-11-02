import { ENVELOPE_VERSION } from '@rediacc/shared/config-crypto';
import {
  E2E_CONTENT_TYPE,
  type E2eRequestEnvelope,
  openRequest,
  sealResponse,
} from '@rediacc/shared/e2e';
import { describe, expect, it } from 'vitest';
import { VERSION } from '../../../version.js';
import { configServerFetch } from '../config-server-client.js';

/** A tunnel server that opens the request, records the inner headers and answers 200 `{}`. */
async function recordingTunnel() {
  const pair = (await crypto.subtle.generateKey({ name: 'X25519' }, true, [
    'deriveBits',
  ])) as CryptoKeyPair;
  const seen: Record<string, string>[] = [];
  const fetchImpl = (async (_url: string, init: RequestInit) => {
    expect((init.headers as Record<string, string>)['Content-Type']).toBe(E2E_CONTENT_TYPE);
    const { innerRequest, aesKey } = await openRequest(
      pair.privateKey,
      JSON.parse(init.body as string) as E2eRequestEnvelope
    );
    seen.push(innerRequest.headers);
    const envelope = await sealResponse(aesKey, 200, '{}');
    return new Response(JSON.stringify(envelope), { status: 200 });
  }) as unknown as typeof fetch;
  return { seen, fetchImpl, serverKey: { key: pair.publicKey, keyId: 'test-key' } };
}

describe('configServerFetch declares what the client reads', () => {
  it.each([
    ['GET', undefined],
    ['PUT', { a: 1 }],
  ])('a %s carries x-cli-version and x-config-envelope', async (method, body) => {
    const { seen, fetchImpl, serverKey } = await recordingTunnel();
    await configServerFetch('/account/api/v1/configs/c1', {
      method,
      body,
      configToken: 'rct_x',
      serverUrl: 'https://account.example.test',
      fetchImpl,
      serverKey,
    });
    expect(seen).toHaveLength(1);
    expect(seen[0]['x-cli-version']).toBe(VERSION);
    expect(seen[0]['x-config-envelope']).toBe(String(ENVELOPE_VERSION));
    expect(seen[0]['X-Config-Token']).toBe('rct_x');
  });
});
