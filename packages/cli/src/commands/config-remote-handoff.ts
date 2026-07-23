/**
 * Handoff payload contract + X25519 helpers for `config remote enable`.
 *
 * Lives in its own module so the round-trip contract test can import the
 * payload shape and decrypt path without dragging in commander. The portal
 * side produces this payload (sealed with cekHandoffEncrypt to the X25519
 * public key the CLI puts in the URL); its mirror fixture lives at
 * `private/account/web/src/lib/__tests__/config-handoff.test.ts` — keep the
 * two textually identical.
 */

import type { CekHandoffBlob } from '@rediacc/shared/config-crypto';
import { toBase64 } from '@rediacc/shared/config-crypto';

/**
 * Decrypted handoff payload from the portal. `configId` is absent for a
 * fresh (zero-config) store — the CLI then mints one from the local config's
 * id and seeds the store on enable.
 */
export interface HandoffPayload {
  passkey_secret: string;
  token: string;
  storageKeyId: string;
  wrappedCek: string;
  storeId: string;
  apiUrl: string;
  configId?: string;
  teamId?: string;
}

export function generateX25519KeyPair(): Promise<CryptoKeyPair> {
  return crypto.subtle.generateKey({ name: 'X25519' }, true, ['deriveBits']);
}

export async function exportPublicKeyBase64(publicKey: CryptoKey): Promise<string> {
  const spki = new Uint8Array(await crypto.subtle.exportKey('spki', publicKey));
  return toBase64(spki);
}

export async function decryptHandoff(
  encryptedBlob: CekHandoffBlob,
  privateKey: CryptoKey
): Promise<HandoffPayload> {
  const { cekHandoffDecrypt } = await import('@rediacc/shared/config-crypto');
  const plainBytes = await cekHandoffDecrypt(encryptedBlob, privateKey);
  const json = new TextDecoder().decode(plainBytes);
  return JSON.parse(json) as HandoffPayload;
}
