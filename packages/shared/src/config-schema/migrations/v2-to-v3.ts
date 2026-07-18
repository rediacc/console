/**
 * Config schema v2 → v3 migration (R2-F6).
 *
 * v3 splits the document into a spec half and a `state` half, keys repositories
 * by name into families of structural tags, retires the `machines[*].ceph`
 * pointer and the composite `name:tag` repo keys, and replaces the compound
 * `/resources` encryption blob with per-field encryption-at-rest.
 *
 * The 10 transforms (spec 04 §3.2) are applied on an in-memory copy; the
 * caller (ConfigFileStorage.load) performs the single atomic persist, so a
 * migration that throws (wrong master password, secret over cap, ambiguous
 * repo keys) leaves the on-disk file untouched and is re-runnable.
 */

import {
  SECRET_AGGREGATE_MAX_BYTES,
  SECRET_ENV_VALUE_MAX_BYTES,
  SECRET_FILE_VALUE_MAX_BYTES,
  utf8ByteLength,
} from '../schemas.js';
import type { MigrationContext } from './index.js';

type Obj = Record<string, unknown>;

// Per-record status fields that move from the repo record into `state.repos`.
const REPO_STATE_FIELDS = [
  'networkId',
  'pushState',
  'headCommit',
  'commitMessage',
  'commitAuthor',
  'commitParent',
  'head',
  'branches',
  'reflog',
] as const;

// Per-record spec fields that stay on the v3 RepoRecord.
const REPO_SPEC_FIELDS = [
  'repositoryGuid',
  'credential',
  'grandGuid',
  'parentGuid',
  'immutable',
  'sshPrivateKey',
  'sshPublicKey',
  'secrets',
] as const;

function isObj(v: unknown): v is Obj {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function warn(message: string): void {
  // console.warn goes to stderr on Node and is the one warn channel that also
  // exists in Workers and browsers, so this module stays runtime-portable.
  console.warn(`config migration (v2→v3): ${message}`);
}

/** Split a v2 composite repo key on the first ':' (bare → tag 'latest'). */
function parseRef(key: string): { name: string; tag: string; grandish: boolean } {
  const idx = key.indexOf(':');
  if (idx === -1) return { name: key, tag: 'latest', grandish: true };
  const tag = key.slice(idx + 1);
  return { name: key.slice(0, idx), tag, grandish: tag === 'latest' };
}

function pick(rec: Obj, keys: readonly string[]): Obj {
  const out: Obj = {};
  for (const k of keys) {
    if (rec[k] !== undefined) out[k] = rec[k];
  }
  return out;
}

/** Lay a decrypted v2 LocalState blob's contents into cfg.resources/credentials. */
function layDecrypted(cfg: Obj, dec: Obj): void {
  const resources = isObj(cfg.resources) ? { ...cfg.resources } : {};
  for (const k of ['machines', 'storages', 'repositories', 'deletedRepositories']) {
    if (dec[k] !== undefined) resources[k] = dec[k];
  }
  cfg.resources = resources;
  if (isObj(dec.sshContent)) {
    cfg.credentials = { ...(isObj(cfg.credentials) ? cfg.credentials : {}), ssh: dec.sshContent };
  }
}

/** Transform 5: unpack the v2 compound `/resources` blob into plaintext. */
async function unpackCompoundBlob(cfg: Obj, ctx: MigrationContext): Promise<void> {
  const encryption = isObj(cfg.encryption) ? cfg.encryption : undefined;
  const fields =
    encryption && isObj(encryption.encryptedFields) ? encryption.encryptedFields : undefined;
  const blob = fields?.['/resources'];
  if (encryption?.mode !== 'master-password' || !fields || !isObj(blob)) return;

  // Real v2 persisted the whole combined base64 under `nonce` (a broken split);
  // accept `data`/`ciphertext` too so any historical shape round-trips.
  const combined = (blob.data ?? blob.ciphertext ?? blob.nonce) as string | undefined;
  if (!combined) return;

  const password = await ctx.getMasterPassword();
  // Throws on a wrong password → migration aborts, file untouched, re-runnable.
  const json = await ctx.decryptLegacyBlob(combined, password);
  layDecrypted(cfg, JSON.parse(json) as Obj);
  delete fields['/resources'];
}

type TagEntry = { tag: string; grandish: boolean; rec: Obj };

/** Choose a grand tag when no bare/latest record survived (lexicographic + warn). */
function fallbackGrand(base: string, tags: Obj): string {
  const grand = [...Object.keys(tags)].sort()[0];
  warn(`repository "${base}" has no grand (production) record; pointing grand at tag "${grand}".`);
  return grand;
}

/** Build one v3 family (+ its state entry) from the v2 records sharing a base name. */
function buildFamily(base: string, list: TagEntry[], families: Obj, stateRepos: Obj): void {
  const grandish = list.filter((x) => x.grandish);
  if (grandish.length > 1) {
    throw new Error(
      `Cannot migrate repository "${base}": both a bare "${base}" and a "${base}:latest" key exist (already ambiguous in v2). Remove one with 'rdc repo delete <ref>' before upgrading.`
    );
  }

  const tags: Obj = {};
  const statePerTag: Obj = {};
  for (const { tag, rec } of list) {
    tags[tag] = pick(rec, REPO_SPEC_FIELDS);
    const st = pick(rec, REPO_STATE_FIELDS);
    if (Object.keys(st).length > 0) statePerTag[tag] = st;
  }

  const grand = grandish.length === 1 ? grandish[0].tag : fallbackGrand(base, tags);
  families[base] = { grand, tags };
  if (Object.keys(statePerTag).length > 0) stateRepos[base] = statePerTag;
}

/** Transforms 2 + 4 (repo half): composite keys → families, status → state. */
function familyizeRepositories(cfg: Obj, stateRepos: Obj): void {
  const resources = isObj(cfg.resources) ? cfg.resources : undefined;
  if (!resources || !isObj(resources.repositories)) return;

  const byBase = new Map<string, TagEntry[]>();
  for (const [key, rawRec] of Object.entries(resources.repositories)) {
    if (!isObj(rawRec)) continue;
    const { name, tag, grandish } = parseRef(key);
    const list = byBase.get(name) ?? [];
    list.push({ tag, grandish, rec: rawRec });
    byBase.set(name, list);
  }

  const families: Obj = {};
  for (const [base, list] of byBase) buildFamily(base, list, families, stateRepos);
  resources.repositories = families;
}

/** Byte size of one secret value, throwing if it exceeds its per-mode cap. */
function secretValueBytes(
  base: string,
  tag: string,
  key: string,
  entry: Obj
): { env: number; file: number } {
  if (typeof entry.value !== 'string') return { env: 0, file: 0 };
  const bytes = utf8ByteLength(entry.value);
  const cap = entry.mode === 'env' ? SECRET_ENV_VALUE_MAX_BYTES : SECRET_FILE_VALUE_MAX_BYTES;
  if (bytes > cap) {
    throw new Error(
      `Cannot migrate secret "${key}" on ${base}:${tag}: ${bytes} bytes exceeds the ${String(entry.mode)}-mode cap of ${cap} bytes. Move the payload to the data plane before upgrading.`
    );
  }
  return entry.mode === 'env' ? { env: bytes, file: 0 } : { env: 0, file: bytes };
}

/** Per-repo-tag secret cap check (transform 8), throwing on the first violation. */
function checkSecretCaps(base: string, tag: string, secrets: Obj): void {
  let envTotal = 0;
  let fileTotal = 0;
  for (const [key, entry] of Object.entries(secrets)) {
    if (!isObj(entry)) continue;
    const { env, file } = secretValueBytes(base, tag, key, entry);
    envTotal += env;
    fileTotal += file;
  }
  if (envTotal > SECRET_AGGREGATE_MAX_BYTES || fileTotal > SECRET_AGGREGATE_MAX_BYTES) {
    throw new Error(
      `Cannot migrate ${base}:${tag}: per-mode secret aggregate exceeds ${SECRET_AGGREGATE_MAX_BYTES} bytes.`
    );
  }
}

/** Check every tag's secrets within one family. */
function checkFamilySecretCaps(base: string, family: Obj): void {
  if (!isObj(family.tags)) return;
  for (const [tag, rec] of Object.entries(family.tags)) {
    if (isObj(rec) && isObj(rec.secrets)) checkSecretCaps(base, tag, rec.secrets);
  }
}

/** Transform 8: re-validate per-secret and per-mode aggregate caps. */
function revalidateSecretCaps(cfg: Obj): void {
  const resources = isObj(cfg.resources) ? cfg.resources : undefined;
  const repos = resources && isObj(resources.repositories) ? resources.repositories : undefined;
  if (!repos) return;
  for (const [base, family] of Object.entries(repos)) {
    if (isObj(family)) checkFamilySecretCaps(base, family);
  }
}

/** Transform 9: split archived-repo composite `name` into `{ name, tag }`. */
function splitDeletedRepoNames(cfg: Obj): void {
  const resources = isObj(cfg.resources) ? cfg.resources : undefined;
  if (!resources) return;
  const deleted = Array.isArray(resources.deletedRepositories)
    ? (resources.deletedRepositories as unknown[])
    : undefined;
  if (!deleted) return;
  resources.deletedRepositories = deleted.map((entry) => {
    if (!isObj(entry) || typeof entry.name !== 'string') return entry;
    const { name, tag } = parseRef(entry.name);
    const spec = pick(entry, REPO_SPEC_FIELDS);
    return { ...spec, name, tag, deletedAt: entry.deletedAt };
  });
}

/** Move one cluster's kvm.memberIds into the state bucket, if present. */
function moveClusterMemberIds(cn: string, cluster: Obj, stateClusters: Obj): void {
  if (!isObj(cluster.kvm) || cluster.kvm.memberIds === undefined) return;
  stateClusters[cn] = {
    ...(isObj(stateClusters[cn]) ? stateClusters[cn] : {}),
    memberIds: cluster.kvm.memberIds,
  };
  delete cluster.kvm.memberIds;
}

/** Transform 4 (cluster half): clusters[*].kvm.memberIds → state.clusters. */
function extractClusterMemberIds(cfg: Obj, state: Obj): void {
  const clusters =
    isObj(cfg.resources) && isObj(cfg.resources.clusters) ? cfg.resources.clusters : undefined;
  if (!clusters) return;
  const stateClusters: Obj = isObj(state.clusters) ? { ...state.clusters } : {};
  for (const [cn, cluster] of Object.entries(clusters)) {
    if (isObj(cluster)) moveClusterMemberIds(cn, cluster, stateClusters);
  }
  if (Object.keys(stateClusters).length > 0) state.clusters = stateClusters;
}

/** Transform 4 (rest): counter + cert cache + cluster memberIds → state. */
function extractStateBuckets(cfg: Obj, state: Obj): void {
  if (isObj(cfg.defaults) && cfg.defaults.nextNetworkId !== undefined) {
    state.networkIds = { next: cfg.defaults.nextNetworkId };
    delete cfg.defaults.nextNetworkId;
  }
  if (isObj(cfg.infra) && cfg.infra.acmeCertCache !== undefined) {
    state.certCache = cfg.infra.acmeCertCache;
    delete cfg.infra.acmeCertCache;
  }
  extractClusterMemberIds(cfg, state);
}

/** Transform 6: residue sweep (R2-F9). */
function residueSweep(cfg: Obj): void {
  if (isObj(cfg.defaults)) delete cfg.defaults.machine;
  if (isObj(cfg.account)) {
    delete cfg.account.team;
    delete cfg.account.region;
  }
}

/** Transform 7: machines[*].ceph retirement (drop with warning). */
function dropMachineCeph(cfg: Obj): void {
  const machines =
    isObj(cfg.resources) && isObj(cfg.resources.machines) ? cfg.resources.machines : undefined;
  if (!machines) return;
  for (const [mn, machine] of Object.entries(machines)) {
    if (!isObj(machine) || machine.ceph === undefined) continue;
    const ceph = isObj(machine.ceph) ? machine.ceph : {};
    const pool = typeof ceph.pool === 'string' ? ceph.pool : '<pool>';
    warn(
      `machine "${mn}": dropped ceph pointer. Re-declare it with 'rdc datastore create <name> --cluster <c> --pool ${pool}'.`
    );
    delete machine.ceph;
  }
}

export async function migrateV2ToV3(raw: Obj, ctx: MigrationContext): Promise<Obj> {
  const cfg = structuredClone(raw);
  cfg.schemaVersion = 3; // 1. Stamp version.

  const state: Obj = isObj(cfg.state) ? { ...cfg.state } : {};
  const stateRepos: Obj = isObj(state.repos) ? { ...state.repos } : {};

  await unpackCompoundBlob(cfg, ctx); // 5 (before familyizing the repos it contains)
  familyizeRepositories(cfg, stateRepos); // 2 + 4 (repo half)
  if (Object.keys(stateRepos).length > 0) state.repos = stateRepos;

  extractStateBuckets(cfg, state); // 4 (rest)
  residueSweep(cfg); // 6
  dropMachineCeph(cfg); // 7
  revalidateSecretCaps(cfg); // 8
  splitDeletedRepoNames(cfg); // 9

  if (Object.keys(state).length > 0) cfg.state = state;
  return cfg;
}
