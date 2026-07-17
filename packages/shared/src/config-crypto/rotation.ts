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
import { buildConfigPushPayload, decryptConfigPullPayload } from '../config-schema/index.js';
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
 * Project a decrypted envelope back onto the config document.
 *
 * A pull only carries the encrypted halves (every `resources` family, ssh,
 * policy, org secrets — the SENSITIVE_FIELDS list); the rest of an RdcConfig
 * is host-local and never leaves the client. The
 * commitment pointers are rooted at the DOCUMENT, though, so re-encryption has
 * to rebuild this shape before it can recompute them.
 *
 * This mirrors `RemoteConfigAdapter.pull()` exactly. It has to: the commitment
 * pointer set it produces is what the server's anti-downgrade check compares the
 * next push against, so a rotation that reconstructed a different shape would
 * either drop a committed pointer (rejected) or commit one the CLI never does
 * (rejected on the CLI's next push).
 */
/**
 * credentials: ssh keys and/or the Cloudflare DNS token. The key is emitted only
 * when at least one is present.
 *
 * Every branch is SPREAD-IF-PRESENT, never `key: value ?? undefined`. The schema
 * walker keys off property EXISTENCE, so an explicit-undefined key commits a
 * phantom pointer the blob cannot back, and the next ordinary push then looks
 * like it dropped a sensitive path — anti-downgrade rejects it and config push
 * bricks for the whole org. Two bugs of exactly this shape have already been
 * caught; this rebuild must not plant a third.
 */
function buildCredentials(decrypted: FullConfig): Record<string, unknown> {
  const credentials: Record<string, unknown> = {};
  const ssh = decrypted.ssh;
  if (ssh?.privateKey) {
    credentials.ssh = {
      privateKey: ssh.privateKey as string,
      ...(ssh.publicKey === undefined ? {} : { publicKey: ssh.publicKey as string }),
      ...(ssh.knownHosts === undefined ? {} : { knownHosts: ssh.knownHosts as string }),
    };
  }
  if (decrypted.cfDnsApiToken !== undefined) credentials.cfDnsApiToken = decrypted.cfDnsApiToken;
  return credentials;
}

/**
 * The `resources` block. machines/repositories/storages always come back;
 * the remaining v3 families ride in the blob (SENSITIVE_FIELDS) and must come
 * back out here, or a pull/rotation silently loses them. Spread-if-present:
 * their leaves are public (uncommitted) EXCEPT deletedRepositories and
 * cloudProviders, whose pointers are committed — an explicit-undefined key here
 * would commit pointers the blob cannot back. Same discipline as buildCredentials.
 */
function buildResources(decrypted: FullConfig): NonNullable<RdcConfig['resources']> {
  return {
    machines: (decrypted.machines ?? {}) as NonNullable<
      NonNullable<RdcConfig['resources']>['machines']
    >,
    repositories: (decrypted.repositories ?? {}) as NonNullable<
      NonNullable<RdcConfig['resources']>['repositories']
    >,
    storages: (decrypted.storages ?? {}) as NonNullable<
      NonNullable<RdcConfig['resources']>['storages']
    >,
    ...(decrypted.datastores === undefined
      ? {}
      : {
          datastores: decrypted.datastores as NonNullable<
            NonNullable<RdcConfig['resources']>['datastores']
          >,
        }),
    ...(decrypted.clusters === undefined
      ? {}
      : {
          clusters: decrypted.clusters as NonNullable<
            NonNullable<RdcConfig['resources']>['clusters']
          >,
        }),
    ...(decrypted.backupStrategies === undefined
      ? {}
      : {
          backupStrategies: decrypted.backupStrategies as NonNullable<
            NonNullable<RdcConfig['resources']>['backupStrategies']
          >,
        }),
    ...(decrypted.deletedRepositories === undefined
      ? {}
      : {
          deletedRepositories: decrypted.deletedRepositories as NonNullable<
            NonNullable<RdcConfig['resources']>['deletedRepositories']
          >,
        }),
    ...(decrypted.cloudProviders === undefined
      ? {}
      : {
          cloudProviders: decrypted.cloudProviders as NonNullable<
            NonNullable<RdcConfig['resources']>['cloudProviders']
          >,
        }),
  };
}

export function fullConfigToRdcConfig(decrypted: FullConfig): RdcConfig {
  const credentials = buildCredentials(decrypted);

  // Spread-if-present throughout (see buildCredentials for why property
  // existence is load-bearing). Committed top-level sections (account.userEmail,
  // defaults.universalUser, infra.*) and '/policy' must come back out or the
  // re-push commits fewer pointers than the server stored.
  const rebuilt = {
    schemaVersion: 3,
    id: decrypted.id,
    version: decrypted.version,
    ...(decrypted.account === undefined
      ? {}
      : { account: decrypted.account as RdcConfig['account'] }),
    ...(decrypted.defaults === undefined
      ? {}
      : { defaults: decrypted.defaults as RdcConfig['defaults'] }),
    ...(decrypted.infra === undefined ? {} : { infra: decrypted.infra as RdcConfig['infra'] }),
    resources: buildResources(decrypted),
    ...(decrypted.policy === undefined ? {} : { policy: decrypted.policy }),
    ...(Object.keys(credentials).length > 0 ? { credentials } : {}),
    encryption: { mode: 'plaintext' },
  };
  return rebuilt as RdcConfig;
}

/**
 * Re-encrypt one pulled config under a new CEK.
 *
 * The field-commitment key is derived from the CEK, so every commitment in the
 * envelope changes with the key. A fresh FCK salt is generated (by omitting
 * `fckSalt`) rather than reused: the commitments have to be recomputed anyway,
 * and a new salt makes it obvious that the old envelope's HMACs are dead.
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
  teamId?: string;
}): Promise<EncryptedConfigPayload> {
  const decrypted = await decryptConfigPullPayload(params.pulled, {
    cek: params.oldCek,
    sdkDerived: params.sdkDerivedForPull,
  });

  return buildConfigPushPayload(fullConfigToRdcConfig(decrypted), {
    version: params.version,
    sdkEpoch: params.sdkEpoch,
    sdkDerived: params.sdkDerivedForPush,
    cek: params.newCek,
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
