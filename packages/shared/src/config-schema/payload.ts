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
import { type RdcConfig, RdcConfigSchema } from './schemas.js';
import { DEVICE_LOCAL_POINTERS } from './sensitivity.js';
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

/** Envelope keys: the plaintext half of a `FullConfig`, never part of the synced document's blob. */
const ENVELOPE_KEYS: ReadonlySet<string> = new Set([
  'envelopeVersion',
  'id',
  'version',
  'sdkEpoch',
  'teamId',
  'orgId',
  'lastModified',
  'commitments',
]);

/**
 * Document roots whose children ride one level up in the blob: `resources.machines` travels as
 * `machines`, `credentials.ssh` as `ssh`. That is the v2 wire encoding every existing blob uses; it
 * is structural (every child is hoisted, none is chosen), so it decides WHERE a key travels, never
 * WHETHER it does.
 */
const HOISTED_ROOTS = ['resources', 'credentials'] as const;
type HoistedRoot = (typeof HOISTED_ROOTS)[number];

/** Child keys the schema declares under a hoisted root, unwrapping `.optional()`. */
function schemaChildKeys(root: HoistedRoot): ReadonlySet<string> {
  let schema = (RdcConfigSchema.shape as Record<string, unknown>)[root] as {
    unwrap?: () => unknown;
    shape?: Record<string, unknown>;
  };
  while (schema.unwrap && !schema.shape) schema = schema.unwrap() as typeof schema;
  return new Set(Object.keys(schema.shape ?? {}));
}

const HOISTED_CHILDREN: Record<HoistedRoot, ReadonlySet<string>> = {
  resources: schemaChildKeys('resources'),
  credentials: schemaChildKeys('credentials'),
};

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/** Remove the value at a one- or two-segment pointer, cloning the parent it edits. */
function omitPointer(doc: Record<string, unknown>, pointer: string): void {
  const [root, child] = pointer.split('/').slice(1);
  if (child === undefined) {
    delete doc[root];
    return;
  }
  const parent = doc[root];
  if (!isPlainObject(parent) || !(child in parent)) return;
  const { [child]: _dropped, ...rest } = parent;
  doc[root] = rest;
}

/**
 * The synced half of a config: the whole document minus DEVICE_LOCAL_POINTERS (sensitivity.ts), the
 * one exclusion list. Everything else travels, `state` and keys this CLI does not know included.
 * Undefined-valued keys are dropped (spread-if-present): the walker keys off property EXISTENCE, so
 * an explicit-undefined key would commit a pointer the blob cannot back.
 */
export function syncedDocument(config: RdcConfig): Record<string, unknown> {
  const doc: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(config as Record<string, unknown>)) {
    if (value !== undefined) doc[key] = value;
  }
  for (const pointer of DEVICE_LOCAL_POINTERS) omitPointer(doc, pointer);
  return doc;
}

/** The blob half of the wire encoding: the synced document, hoisted roots flattened one level. */
function encodeBlobSections(synced: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const put = (key: string, value: unknown) => {
    if (value === undefined) return;
    // Two document paths landing on one wire key would silently overwrite each other.
    if (key in out || ENVELOPE_KEYS.has(key)) {
      throw new Error(`Config wire encoding: "${key}" would be carried twice`);
    }
    out[key] = value;
  };
  for (const [key, value] of Object.entries(synced)) {
    if (key === 'id') continue; // the envelope carries it
    if ((HOISTED_ROOTS as readonly string[]).includes(key) && isPlainObject(value)) {
      for (const [child, childValue] of Object.entries(value)) put(child, childValue);
    } else {
      put(key, value);
    }
  }
  return out;
}

/**
 * Project an `RdcConfig` into the `FullConfig` shape the crypto layer encrypts: the envelope plus
 * `syncedDocument(config)` in the wire encoding. There is no per-section list here; a new schema key
 * syncs by default, and only DEVICE_LOCAL_POINTERS stay home.
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
    ...encodeBlobSections(syncedDocument(config)),
  };
}

/**
 * Inverse of `toFullConfig`: rebuild the config document from a decrypted envelope. A blob key the
 * schema declares under a hoisted root goes back under it; every other key is a top-level section.
 * The three core resource families come back as `{}` when absent, and `encryption` as a plaintext
 * placeholder the device overlay replaces (it is device-local).
 *
 * Spread-if-present throughout: only keys the blob carries are written, so the rebuilt document
 * commits exactly the pointer set the pushed one did.
 */
export function fromFullConfig(decrypted: FullConfig): RdcConfig {
  const resources: Record<string, unknown> = { machines: {}, repositories: {}, storages: {} };
  const credentials: Record<string, unknown> = {};
  const doc: Record<string, unknown> = {
    schemaVersion: 3,
    id: decrypted.id,
    version: decrypted.version,
  };
  for (const [key, value] of Object.entries(decrypted)) {
    if (ENVELOPE_KEYS.has(key) || value === undefined) continue;
    if (HOISTED_CHILDREN.resources.has(key)) resources[key] = value;
    else if (HOISTED_CHILDREN.credentials.has(key)) credentials[key] = value;
    else doc[key] = value;
  }
  doc.resources = resources;
  if (Object.keys(credentials).length > 0) doc.credentials = credentials;
  doc.encryption = { mode: 'plaintext' };
  return doc as RdcConfig;
}

/**
 * Compose the encrypted payload for a config push: commitments from the schema
 * walker, envelope from the document, ciphertext from the crypto layer.
 */
export function buildConfigPushPayload(
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
  // The blob is JSON, so the commitments are computed over the JSON form too: an explicit-undefined
  // key anywhere (a `knownHosts: undefined` in a rebuilt ssh pair) would otherwise commit a pointer
  // the blob cannot carry, and the next push built from a pulled copy would drop it (anti-downgrade).
  const doc = JSON.parse(JSON.stringify(config)) as RdcConfig;
  const fullConfig = toFullConfig(doc, {
    version: params.version,
    sdkEpoch: params.sdkEpoch,
    teamId: params.teamId,
  });

  return selectiveEncrypt(fullConfig, params.sdkDerived, params.cek, {
    sdkEpoch: params.sdkEpoch,
    fckSalt: params.fckSalt,
    commitEntries: buildCommitEntries(doc),
  });
}

/**
 * Inverse of `buildConfigPushPayload`: decrypt a pulled envelope. `fromFullConfig` turns the result
 * back into a document; the device-local pointers (DEVICE_LOCAL_POINTERS) are absent, because they
 * never left the pushing device. Verifies the HMAC and rejects non-v2 envelopes, both inside
 * `selectiveDecrypt`.
 */
export function decryptConfigPullPayload(
  payload: EncryptedConfigPayload,
  keys: { cek: CryptoKey; sdkDerived: CryptoKey }
): Promise<FullConfig> {
  return selectiveDecrypt(payload, keys.cek, keys.sdkDerived);
}
