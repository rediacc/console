/**
 * Org-wide CEK rotation — the client half.
 *
 * Rotation is a client-side operation by construction: the server never holds
 * the CEK, so it cannot re-encrypt anything. The client pulls every config with
 * the OLD key, re-encrypts each under a NEW key, and hands the server the
 * ciphertext plus the key material every member needs to catch up. The server's
 * only jobs are ordering (nothing was pushed underneath us) and layer 3.
 *
 * The portal wizard and `rdc config rotate-cek` both drive that sequence, so it
 * lives here once rather than twice.
 *
 * ## Why this file is NOT exported from config-crypto/index.ts
 *
 * Re-encrypting a config requires recomputing its field commitments, which is
 * defined over the config DOCUMENT (config-schema), not over raw bytes. So this
 * module depends on config-schema, while config-schema/payload.ts depends on
 * config-crypto. Putting it in the config-crypto barrel would close that loop
 * into an import cycle. Keeping it out of the barrel means the dependency runs
 * one way only — rotation -> config-schema -> config-crypto — and consumers
 * reach it through the '@rediacc/shared/config-crypto/rotation' subpath.
 */

import type { RdcConfig } from '../config-schema/index.js';
import {
  buildConfigPushPayload,
  decryptConfigPullPayload,
  fromFullConfig,
} from '../config-schema/index.js';
import { exportAesKey, fromBase64 } from './aes.js';
import { cekHandoffEncrypt, cekWrap, generateCek } from './index.js';
import type { EncryptedConfigPayload, FullConfig } from './types.js';

/** A config as named by the rotation snapshot the server issued at `begin`. */
export interface RotationConfigRef {
  configId: string;
  teamId: string | null;
  /** The version the server saw at `begin`. The re-encrypted push must be this + 1. */
  version: number;
}

/** A member who must be able to read configs after the rotation. */
export interface RotationIdentity {
  userId: string;
  /** Base64 SPKI, exactly as `config_user_identities.x25519_public_key` stores it. */
  x25519PublicKey: string;
}

/** A new CEK, sealed to one member's X25519 key. */
export interface RotationHandoff {
  targetUserId: string;
  /** JSON-serialized CekHandoffBlob — the encoding the members API already uses. */
  encryptedCek: string;
}

export { generateCek };

/**
 * Narrow a Uint8Array to the ArrayBuffer that Web Crypto's BufferSource wants.
 * Mirrors the helper in handoff.ts: TypeScript models `.buffer` as
 * ArrayBufferLike (possibly SharedArrayBuffer), which BufferSource rejects.
 */
function buf(data: Uint8Array): ArrayBuffer {
  if (data.byteOffset === 0 && data.byteLength === data.buffer.byteLength) {
    return data.buffer as ArrayBuffer;
  }
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

/**
 * Project a decrypted envelope back onto the config document: `fromFullConfig` (payload.ts), the one
 * inverse of the push projection. The CLI pull, the executor, the portal session and the CEK
 * rotation all rebuild through it, so the commitment pointer set a rebuilt document produces is the
 * one the next push commits.
 */
export function fullConfigToRdcConfig(decrypted: FullConfig): RdcConfig {
  return fromFullConfig(decrypted);
}

/**
 * Re-encrypt one pulled config under a new CEK.
 *
 * The field-commitment key and the pointer-blinding key are derived from the CEK, so every
 * commitment and every commitment key in the envelope changes with the key. A fresh FCK salt is
 * generated (by omitting `fckSalt`) rather than reused: the commitments have to be recomputed anyway,
 * and a new salt makes it obvious that the old envelope's HMACs are dead. The server applies no
 * anti-downgrade check to a rotation (the keys cannot match across CEKs), so no prior is sent.
 */
export async function reencryptConfig(params: {
  /** The pulled payload, as assembled from the pull response. */
  pulled: EncryptedConfigPayload;
  oldCek: CryptoKey;
  newCek: CryptoKey;
  /** SDK key for the epoch the config was PULLED at. */
  sdkDerivedForPull: CryptoKey;
  /** SDK key for the CURRENT epoch, which the re-encrypted blob is written under. */
  sdkDerivedForPush: CryptoKey;
  sdkEpoch: number;
  /** Version to write: the snapshot version plus one. */
  version: number;
  /** The store and config being rotated: the AAD binding of both the pulled and the new blob. */
  storeId: string;
  configId: string;
  teamId?: string;
}): Promise<EncryptedConfigPayload> {
  const decrypted = await decryptConfigPullPayload(params.pulled, {
    cek: params.oldCek,
    sdkDerived: params.sdkDerivedForPull,
    binding: { storeId: params.storeId, configId: params.configId, teamId: params.teamId ?? null },
  });

  return buildConfigPushPayload(fullConfigToRdcConfig(decrypted), {
    version: params.version,
    sdkEpoch: params.sdkEpoch,
    sdkDerived: params.sdkDerivedForPush,
    cek: params.newCek,
    storeId: params.storeId,
    teamId: params.teamId,
  });
}

/**
 * Seal a new CEK to everyone who needs it.
 *
 * The initiator gets it wrapped under their own wrapping key (so they keep
 * working without a re-accept); every other member gets an X25519 handoff blob
 * they will accept through the existing pending-handoff flow. The server relays
 * both as opaque strings and can decrypt neither.
 */
export async function distributeNewCek(params: {
  newCek: CryptoKey;
  /** The rotating user — excluded from the handoff list, wrapped directly instead. */
  selfUserId: string;
  /** HKDF(passkey_secret || server_secret) for the rotating user. */
  wrappingKey: CryptoKey;
  identities: RotationIdentity[];
}): Promise<{ wrappedCek: string; handoffs: RotationHandoff[] }> {
  const wrappedCek = await cekWrap(params.newCek, params.wrappingKey);
  const cekRaw = await exportAesKey(params.newCek);

  const handoffs: RotationHandoff[] = [];
  for (const identity of params.identities) {
    if (identity.userId === params.selfUserId) continue;
    const publicKey = await crypto.subtle.importKey(
      'spki',
      buf(fromBase64(identity.x25519PublicKey)),
      { name: 'X25519' },
      false,
      []
    );
    const blob = await cekHandoffEncrypt(cekRaw, publicKey);
    handoffs.push({ targetUserId: identity.userId, encryptedCek: JSON.stringify(blob) });
  }

  return { wrappedCek, handoffs };
}
