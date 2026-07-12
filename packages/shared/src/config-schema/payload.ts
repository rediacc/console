/**
 * Config push/pull payload composition.
 *
 * The bridge between the config DOCUMENT (this package) and the config CRYPTO
 * (packages/shared/src/config-crypto): it turns an `RdcConfig` into the v2
 * envelope the account server accepts, and turns a decrypted envelope back into
 * an `RdcConfig`.
 *
 * It lives here, not in config-crypto, to keep the layering one-directional:
 * config-crypto stays a generic crypto library that knows nothing about the
 * Rediacc config shape, while this module knows both.
 *
 * Three callers must produce byte-identical payloads or pushes will fail the
 * server-side precondition check: the CLI (`adapters/remote-config-adapter.ts`),
 * the web console config editor, and the CEK rotation flow. That is the whole
 * reason this composition is factored out instead of written three times.
 */

import type { EncryptedConfigPayload, FullConfig } from '../config-crypto/index.js';
import { selectiveDecrypt, selectiveEncrypt } from '../config-crypto/index.js';
import type { RdcConfig } from './schemas.js';
import { getByPointer, pathsToCommit } from './walker.js';

/** Pointer/value pairs whose HMACs are committed in the envelope. */
export interface CommitEntry {
  pointer: string;
  value: unknown;
}

/**
 * The commitment set for a config: every sensitive, committable leaf the
 * sensitivity registry knows about, paired with its current value.
 *
 * The server enforces preconditions against these, so the pointer set must be
 * derived from the schema (never hand-listed by a caller).
 */
export function buildCommitEntries(config: RdcConfig): CommitEntry[] {
  return pathsToCommit(config).map((pointer) => ({
    pointer,
    value: getByPointer(config, pointer),
  }));
}

/**
 * Project an `RdcConfig` into the `FullConfig` shape the crypto layer encrypts.
 *
 * `version` is the version being WRITTEN (that is, current + 1). The caller owns
 * the increment because only it knows the version it pulled.
 */
export function toFullConfig(
  config: RdcConfig,
  params: { version: number; sdkEpoch: number; teamId?: string }
): FullConfig {
  return {
    envelopeVersion: 2,
    id: config.id,
    version: params.version,
    sdkEpoch: params.sdkEpoch,
    ...(params.teamId ? { teamId: params.teamId } : {}),
    // Commitments are recomputed inside selectiveEncrypt from commitEntries;
    // this placeholder keeps the type total.
    commitments: { alg: 'HMAC-SHA256', fckSalt: '', fields: {} },
    machines: config.resources?.machines ?? {},
    repositories: config.resources?.repositories ?? {},
    storages: config.resources?.storages ?? {},
    ssh: config.credentials?.ssh,
    // Committed org secrets that must ride inside the ciphertext, or a push/
    // rotation round trip drops them (data loss) and the re-push commits fewer
    // pointers than the server was told to expect (anti-downgrade rejection).
    // Spread-if-present for the same reason ssh/policy are: these paths are in
    // the sensitivity registry, so an explicit-undefined key would commit a
    // pointer the blob cannot back.
    ...(config.resources?.cloudProviders === undefined
      ? {}
      : { cloudProviders: config.resources.cloudProviders }),
    ...(config.credentials?.cfDnsApiToken === undefined
      ? {}
      : { cfDnsApiToken: config.credentials.cfDnsApiToken }),
    // The rules travel INSIDE the ciphertext, because the executor enforces them
    // and the executor only ever sees what the blob carries. Left out, an org's
    // policy never reaches the thing it governs.
    //
    // Spread-if-present, never `policy: config.policy`: '/policy' is in the
    // sensitivity registry, so an explicit-undefined key would commit a pointer
    // the blob cannot back, and the next ordinary push would look like it had
    // dropped a sensitive path. See __tests__/undefined-keys.test.ts.
    ...(config.policy === undefined ? {} : { policy: config.policy }),
  };
}

/**
 * Compose the encrypted payload for a config push: commitments from the schema
 * walker, envelope from the document, ciphertext from the crypto layer.
 */
export async function buildConfigPushPayload(
  config: RdcConfig,
  params: {
    /** Version being written (the pulled version plus one). */
    version: number;
    sdkEpoch: number;
    sdkDerived: CryptoKey;
    cek: CryptoKey;
    teamId?: string;
    /** Reuse a prior field-commitment salt, or omit for a fresh one. */
    fckSalt?: string;
  }
): Promise<EncryptedConfigPayload> {
  const fullConfig = toFullConfig(config, {
    version: params.version,
    sdkEpoch: params.sdkEpoch,
    teamId: params.teamId,
  });

  return selectiveEncrypt(fullConfig, params.sdkDerived, params.cek, {
    sdkEpoch: params.sdkEpoch,
    fckSalt: params.fckSalt,
    commitEntries: buildCommitEntries(config),
  });
}

/**
 * Inverse of `buildConfigPushPayload`: decrypt a pulled envelope back into the
 * sensitive halves of the config (machines, repositories, storages, ssh).
 *
 * Returns `FullConfig` rather than a whole `RdcConfig` because the remaining
 * fields (defaults, state, encryption mode) are host-local and never leave the
 * client. Verifies the HMAC and rejects non-v2 envelopes, both inside
 * `selectiveDecrypt`.
 */
export async function decryptConfigPullPayload(
  payload: EncryptedConfigPayload,
  keys: { cek: CryptoKey; sdkDerived: CryptoKey }
): Promise<FullConfig> {
  return selectiveDecrypt(payload, keys.cek, keys.sdkDerived);
}
