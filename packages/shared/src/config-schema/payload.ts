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
 * Committed top-level sections (userEmail, universalUser, certEmail,
 * cfDnsZoneId): committed means carried, or the first pull/re-push round trip
 * drops them and trips the server's anti-downgrade check. The sections
 * deliberately NOT projected are host-local by design and carry no committed
 * pointers: `remote` (store pointer, commit:false), `state` (runtime half,
 * stripped before push), `encryption` (at-rest metadata), `renetPath` (binary
 * override, public). Spread-if-present, never `key: value ?? undefined`.
 */
function projectTopLevelSections(config: RdcConfig): Partial<FullConfig> {
  return {
    ...(config.account === undefined ? {} : { account: config.account }),
    ...(config.defaults === undefined ? {} : { defaults: config.defaults }),
    ...(config.infra === undefined ? {} : { infra: config.infra }),
  };
}

/**
 * The remaining v3 families. All-public leaves (nothing committed except
 * deletedRepositories' credential pointers), but they must ride in the blob or a
 * push/pull round trip silently loses every datastore, cluster, and
 * backup-strategy definition. Spread-if-present, same discipline as everywhere
 * in this projection.
 */
function projectResourceFamilies(resources: RdcConfig['resources']): Partial<FullConfig> {
  return {
    ...(resources?.datastores === undefined ? {} : { datastores: resources.datastores }),
    ...(resources?.clusters === undefined ? {} : { clusters: resources.clusters }),
    ...(resources?.backupStrategies === undefined
      ? {}
      : { backupStrategies: resources.backupStrategies }),
    ...(resources?.deletedRepositories === undefined
      ? {}
      : { deletedRepositories: resources.deletedRepositories }),
  };
}

/**
 * Committed org secrets and policy that ride inside the ciphertext, or a push/
 * rotation round trip drops them (data loss) and the re-push commits fewer
 * pointers than the server was told to expect (anti-downgrade rejection). These
 * paths are in the sensitivity registry, so an explicit-undefined key would
 * commit a pointer the blob cannot back — spread-if-present only. Policy travels
 * inside the ciphertext because the executor enforces it and only ever sees what
 * the blob carries. See __tests__/undefined-keys.test.ts.
 */
function projectCommittedSecrets(config: RdcConfig): Partial<FullConfig> {
  return {
    ...(config.resources?.cloudProviders === undefined
      ? {}
      : { cloudProviders: config.resources.cloudProviders }),
    ...(config.credentials?.cfDnsApiToken === undefined
      ? {}
      : { cfDnsApiToken: config.credentials.cfDnsApiToken }),
    ...(config.policy === undefined ? {} : { policy: config.policy }),
  };
}

/**
 * Project an `RdcConfig` into the `FullConfig` shape the crypto layer encrypts.
 *
 * `version` is the version being WRITTEN (that is, current + 1). The caller owns
 * the increment because only it knows the version it pulled.
 *
 * The per-section spreads keep the exact key order and spread-if-present
 * discipline the anti-downgrade check depends on; see the helper docs.
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
    ...projectTopLevelSections(config),
    machines: config.resources?.machines ?? {},
    repositories: config.resources?.repositories ?? {},
    storages: config.resources?.storages ?? {},
    ...projectResourceFamilies(config.resources),
    ssh: config.credentials?.ssh,
    ...projectCommittedSecrets(config),
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
 * sensitive halves of the config (every `resources` family, ssh, policy, org
 * secrets — see SENSITIVE_FIELDS).
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
