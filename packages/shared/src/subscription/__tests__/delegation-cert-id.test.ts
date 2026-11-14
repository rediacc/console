import { describe, expect, it } from 'vitest';
import { DELEGATION_CERT_ID_LENGTH, delegationCertId } from '../delegation-cert-id.js';
import { delegationCertId as fromIndex } from '../index.js';

// Vectors from `printf '%s' <payload> | sha256sum | cut -c1-16`; the account
// server's apply tests compare their own ids against this function.
const PAYLOAD = 'eyJ2ZXJzaW9uIjoxfQ==';
const PAYLOAD_ID = '6f2611698dedbb1c';

describe('delegationCertId', () => {
  it('is the first 16 hex characters of SHA-256 over the base64 payload string', async () => {
    expect(await delegationCertId({ payload: PAYLOAD })).toBe(PAYLOAD_ID);
    expect(await delegationCertId({ payload: '' })).toBe('e3b0c44298fc1c14');
  });

  it('ignores the signature and key id, so a re-signed payload keeps its id', async () => {
    const a = await delegationCertId({ payload: PAYLOAD, signature: 'x', publicKeyId: 'k1' } as {
      payload: string;
    });
    expect(a).toBe(PAYLOAD_ID);
  });

  it('is lowercase hex of the declared length and is exported from the subscription index', async () => {
    const id = await fromIndex({ payload: 'other' });
    expect(id).toMatch(new RegExp(`^[0-9a-f]{${DELEGATION_CERT_ID_LENGTH}}$`));
    expect(id).not.toBe(PAYLOAD_ID);
  });
});
