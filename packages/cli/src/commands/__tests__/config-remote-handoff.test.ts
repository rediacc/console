/**
 * Handoff blob contract round-trip (CLI side) — REAL X25519 crypto.
 *
 * This is the executable contract between the CLI and the portal enrollment
 * pages: the portal builds exactly this payload shape and seals it with
 * `cekHandoffEncrypt` to the X25519 public key from the URL; the CLI decrypts
 * with `decryptHandoff`. The web-side mirror fixture lives at
 * `private/account/web/src/lib/__tests__/config-handoff.test.ts` — keep the
 * two payload fixtures textually identical.
 */

import { cekHandoffEncrypt } from '@rediacc/shared/config-crypto';
import { describe, expect, it } from 'vitest';
import {
  decryptHandoff,
  exportPublicKeyBase64,
  generateX25519KeyPair,
  type HandoffPayload,
} from '../config-remote-handoff.js';

/** Seal a payload exactly as the portal pages do (JSON → bytes → X25519 blob). */
async function seal(payload: HandoffPayload, publicKey: CryptoKey) {
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  return cekHandoffEncrypt(bytes, publicKey);
}

// Mirror of the web fixture — keep textually identical with
// private/account/web/src/lib/__tests__/config-handoff.test.ts.
const BASE_PAYLOAD = {
  passkey_secret: 'cGFzc2tleV9zZWNyZXRfMzJfYnl0ZXNfYjY0',
  token: 'rct_rotated_latest',
  storageKeyId: 'rdc:pk:55555555-5555-4555-8555-555555555555',
  wrappedCek: 'd3JhcHBlZF9jZWtfb3BhcXVl',
  storeId: '11111111-1111-4111-8111-111111111111',
  apiUrl: 'https://account.example.com',
};

describe('handoff blob contract round-trip (real X25519)', () => {
  it('round-trips a full payload (existing store: configId + teamId pinned)', async () => {
    const keyPair = await generateX25519KeyPair();
    const payload: HandoffPayload = {
      ...BASE_PAYLOAD,
      configId: '22222222-2222-4222-8222-222222222222',
      teamId: '33333333-3333-4333-8333-333333333333',
    };

    const blob = await seal(payload, keyPair.publicKey);
    const decrypted = await decryptHandoff(blob, keyPair.privateKey);

    expect(decrypted).toEqual(payload);
  });

  it('round-trips a fresh-store payload (configId omitted → CLI mints + seeds)', async () => {
    const keyPair = await generateX25519KeyPair();
    const payload: HandoffPayload = { ...BASE_PAYLOAD };

    const blob = await seal(payload, keyPair.publicKey);
    const decrypted = await decryptHandoff(blob, keyPair.privateKey);

    expect(decrypted).toEqual(payload);
    expect(decrypted.configId).toBeUndefined();
    expect(decrypted.teamId).toBeUndefined();
  });

  it('the exported public key imports back as a usable X25519 recipient key', async () => {
    // The CLI puts exportPublicKeyBase64(publicKey) in the URL; the portal
    // imports it as spki and seals to it. Prove that leg with the same import
    // the portal uses.
    const keyPair = await generateX25519KeyPair();
    const pubBase64 = await exportPublicKeyBase64(keyPair.publicKey);

    const { fromBase64 } = await import('@rediacc/shared/config-crypto');
    const spki = fromBase64(pubBase64);
    const imported = await crypto.subtle.importKey(
      'spki',
      spki.buffer.slice(spki.byteOffset, spki.byteOffset + spki.byteLength) as ArrayBuffer,
      { name: 'X25519' },
      false,
      []
    );

    const payload: HandoffPayload = { ...BASE_PAYLOAD };
    const blob = await seal(payload, imported);
    const decrypted = await decryptHandoff(blob, keyPair.privateKey);
    expect(decrypted).toEqual(payload);
  });

  it('does not decrypt with the wrong private key', async () => {
    const keyPair = await generateX25519KeyPair();
    const otherPair = await generateX25519KeyPair();
    const blob = await seal({ ...BASE_PAYLOAD }, keyPair.publicKey);

    await expect(decryptHandoff(blob, otherPair.privateKey)).rejects.toThrow();
  });
});
