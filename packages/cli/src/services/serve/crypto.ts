/**
 * The X25519 half of the CEK grant, on the executor's side.
 *
 * A fresh keypair is minted per session and the private half never leaves this
 * process. It exists only to open one sealed blob, after which the session drops
 * it (see SessionStore.grantCek).
 *
 * Web Crypto only, so this is the same code path in a container, in a daemon,
 * and in the browser that seals the blob.
 */

import { toBase64 } from '@rediacc/shared/config-crypto';
import type { ServeCrypto } from './deps.js';

export const serveCrypto: ServeCrypto = {
  async generateEphemeralKeyPair() {
    // `false` for extractable: the private half cannot be exported, even by this
    // process, so a bug here cannot leak it. Only the public half goes out.
    const keyPair = await crypto.subtle.generateKey({ name: 'X25519' }, false, ['deriveBits']);

    return { publicKey: keyPair.publicKey, privateKey: keyPair.privateKey };
  },

  async exportPublicKey(key: CryptoKey) {
    const spki = await crypto.subtle.exportKey('spki', key);
    return toBase64(new Uint8Array(spki));
  },
};
