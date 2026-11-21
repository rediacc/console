/**
 * `rdc config prune`, sweep stale leftovers from the local config file.
 *
 * Three buckets, all pure-local (no SSH/renet):
 *
 *   1. ACME cert-cache entries whose anchor (GUID / repo name / machine)
 *      is no longer in the active config.
 *   2. Expired archived repositories, `resources.deletedRepositories[]`
 *      entries whose `deletedAt` is older than `defaults.pruneGraceDays`
 *      (default 7). In-grace entries are kept for accidental-delete
 *      recovery.
 *   3. Dangling cross-references (machine→strategy, strategy→repo).
 *   4. References to a machine the config no longer has (#80f7476a): `state.licenseRefresh` and
 *      `pushState` entries are dropped (runtime records, no secrets); repository entries placed on
 *      such a machine are reported, and archived (credential kept) with `--gone-machine-repos`.
 *
 * Exposes `analyzeConfigPrune(options)` for preview + `applyConfigPrune`
 * for the real run. The analysis return shape feeds directly into the CLI
 * formatter so command-layer code stays thin.
 */

import { gunzipSync, gzipSync } from 'node:zlib';
import type { ArchivedRepository, RdcConfig } from '@rediacc/shared/config-schema';
import { parseRepoRef } from '../../utils/config-schema.js';
import { type ConfigAnchors, pruneCertsByAnchor } from '../account/cert-cache.js';
import { type DroppedRef, pruneDanglingRefs } from './config-refs-prune.js';
import { configService } from './config-resources.js';
import { buildArchivedRecord } from './config-resources-resolve.js';
import { findGoneMachineRepos, type GoneMachineRepo, machineExists } from './machine-gone-repos.js';
import { flattenRepositories } from './resource-state.js';
import { updateSyncedConfig } from './synced-write.js';

/** Default archive grace period if not set in config. Mirrors `prune.ts`. */
const DEFAULT_GRACE_DAYS = 7;
const MS_PER_DAY = 24 * 60 * 60 * 1000;

export interface ConfigPruneOptions {
  /** When false (default), the analysis is computed but no write happens. */
  apply?: boolean;
  /** Restrict to a single bucket. */
  certsOnly?: boolean;
  archivesOnly?: boolean;
  refsOnly?: boolean;
  /** Override the archive grace window for this invocation. */
  graceDays?: number;
  /** Drop in-grace archives too (mirrors `config repository purge-archived`). */
  purgeArchived?: boolean;
  /**
   * Remove repository entries that are placed on no machine. Opt-in: a repo
   * entry carries its LUKS credential and SSH key, so dropping one is
   * unrecoverable if the image turns out to exist somewhere after all.
   */
  orphanRepos?: boolean;
  /**
   * Archive repository entries placed on a machine the config no longer has. Archived, not
   * dropped: the credential stays restorable until the archive grace expires.
   */
  goneMachineRepos?: boolean;
}

export interface CertPruneEntry {
  baseDomain: string;
  name: string;
  reason: string;
}

export interface ArchiveGraceEntry {
  name: string;
  guid: string;
  daysAgo: number;
  daysRemaining: number;
}

export interface ConfigPruneAnalysis {
  /** Cert names that would be (or were) removed from the cache. */
  staleCerts: CertPruneEntry[];
  /** Archived repos whose grace expired and would be (or were) purged. */
  expiredArchives: ArchivedRepository[];
  /** Archived repos still in grace, kept, listed for visibility. */
  graceArchives: ArchiveGraceEntry[];
  /** Cross-reference values that would be (or were) dropped. */
  droppedRefs: DroppedRef[];
  /** Soft warnings: references flagged rather than auto-removed (none since the storages family was retired). */
  warnings: string[];
  /**
   * Repository entries placed on no machine. Always reported; only removed when
   * `orphanRepos` is set.
   */
  orphanRepos: OrphanRepoEntry[];
  /** `state.repos` records whose repository entry no longer exists. */
  orphanStateRepos: OrphanStateRepo[];
  /**
   * Repository entries placed on a machine the config no longer has. Always reported; archived
   * only when `goneMachineRepos` is set.
   */
  goneMachineRepos: GoneMachineRepo[];
  /** Runtime records naming a machine the config no longer has, as JSON-ish paths; always dropped. */
  goneMachineState: string[];
}

export interface OrphanRepoEntry {
  name: string;
  /** Grand tag's GUID, for cross-checking against a machine before removing. */
  guid?: string;
}

/**
 * Names dropped from `state.repos` because no resource entry owns them.
 *
 * Unlike a repository entry, a state record holds only runtime status
 * (networkId, registryPort, pushState, headCommit, branches, reflog) and no
 * secrets, so it is pruned unconditionally rather than behind an opt-in flag.
 */
export type OrphanStateRepo = string;

/**
 * Build the set of live anchors from the active config. Archived repos are
 * intentionally treated as live so their certs survive the grace window ,
 * an operator restoring an archive shouldn't have to re-issue certs.
 *
 * Exported for test access; the apply path also uses it via the closure.
 */
/** Collect every declared repository GUID + base name from the live families. */
function collectLiveRepoAnchors(
  config: RdcConfig,
  guids: Set<string>,
  repoNames: Set<string>
): void {
  for (const [name, family] of Object.entries(config.resources?.repositories ?? {})) {
    for (const record of Object.values(family.tags)) {
      if (record.repositoryGuid) guids.add(record.repositoryGuid);
    }
    repoNames.add(name);
  }
}

export function buildConfigAnchors(config: RdcConfig): ConfigAnchors {
  const guids = new Set<string>();
  const repoNames = new Set<string>();
  const machines = new Set<string>();

  collectLiveRepoAnchors(config, guids, repoNames);
  for (const archived of config.resources?.deletedRepositories ?? []) {
    if (archived.repositoryGuid) guids.add(archived.repositoryGuid);
    if (archived.name) repoNames.add(parseRepoRef(archived.name).name);
  }
  for (const machineName of Object.keys(config.resources?.machines ?? {})) {
    machines.add(machineName);
  }

  return { guids, repoNames, machines };
}

/** Decompress the cache's `data` field back into the raw acme.json string. */
function decompressCacheData(data: string | string[]): string {
  const b64 = Array.isArray(data) ? data.join('') : data;
  const buf = Buffer.from(b64, 'base64');
  return gunzipSync(buf).toString('utf8');
}

/** Recompress raw acme.json into the cache's `data`/`rawSize` fields. */
function compressCacheData(raw: string): { data: string | string[]; rawSize: number } {
  const compressed = gzipSync(Buffer.from(raw, 'utf8'), { level: 9 });
  const b64 = compressed.toString('base64');
  const CHUNK_SIZE = 48 * 1024;
  if (b64.length <= CHUNK_SIZE) {
    return { data: b64, rawSize: raw.length };
  }
  const chunks: string[] = [];
  for (let i = 0; i < b64.length; i += CHUNK_SIZE) {
    chunks.push(b64.slice(i, i + CHUNK_SIZE));
  }
  return { data: chunks, rawSize: raw.length };
}

/**
 * Apply the cert-name prune to every `infra.acmeCertCache.<baseDomain>`
 * bucket in the config. Mutates the passed config in-place. Returns the
 * collected cert-removal entries.
 *
 * Exported for test access; this is the riskiest part of `config prune`
 * because it round-trips through gzip/base64 chunking and rebuilds the
 * derived `certs` map + `certCount`.
 */
function safeDecodeBucket(data: string | string[]): Record<string, unknown> | undefined {
  let raw: string;
  try {
    raw = decompressCacheData(data);
  } catch {
    return undefined;
  }
  try {
    return JSON.parse(raw);
  } catch {
    return undefined;
  }
}

function rebuildCertsMap(
  cleaned: Record<string, unknown>,
  prevCerts: Record<string, string>
): Record<string, string> {
  const newCerts: Record<string, string> = {};
  for (const resolver of Object.values(cleaned) as {
    Certificates?: { domain: { main: string }; certificate: string }[];
  }[]) {
    for (const cert of resolver.Certificates ?? []) {
      const prev = prevCerts[cert.domain.main];
      if (prev) newCerts[cert.domain.main] = prev;
    }
  }
  return newCerts;
}

export function pruneCertCacheBuckets(config: RdcConfig, anchors: ConfigAnchors): CertPruneEntry[] {
  const removed: CertPruneEntry[] = [];
  const cache = config.state?.certCache;
  if (!cache) return removed;

  for (const [baseDomain, bucket] of Object.entries(cache)) {
    const acme = safeDecodeBucket(bucket.data);
    if (!acme) continue;

    const result = pruneCertsByAnchor(
      acme as Parameters<typeof pruneCertsByAnchor>[0],
      baseDomain,
      anchors
    );
    if (result.removedCount === 0) continue;

    for (const r of result.removed) {
      removed.push({ baseDomain, name: r.name, reason: r.reason });
    }

    const repacked = compressCacheData(JSON.stringify(result.cleaned));
    const newCerts = rebuildCertsMap(result.cleaned, bucket.certs);

    bucket.data = repacked.data;
    bucket.rawSize = repacked.rawSize;
    bucket.certs = newCerts;
    bucket.certCount = Object.keys(newCerts).length;
    bucket.updatedAt = new Date().toISOString();
  }

  return removed;
}

/** Categorize archives as expired vs in-grace based on `deletedAt`. */
export function classifyArchives(
  archives: ArchivedRepository[],
  graceDays: number,
  now: Date = new Date()
): { expired: ArchivedRepository[]; inGrace: ArchiveGraceEntry[] } {
  const cutoffMs = now.getTime() - graceDays * MS_PER_DAY;
  const expired: ArchivedRepository[] = [];
  const inGrace: ArchiveGraceEntry[] = [];
  for (const a of archives) {
    const ts = Date.parse(a.deletedAt);
    if (Number.isNaN(ts)) continue;
    if (ts < cutoffMs) {
      expired.push(a);
    } else {
      const daysAgo = Math.floor((now.getTime() - ts) / MS_PER_DAY);
      inGrace.push({
        name: a.name,
        guid: a.repositoryGuid,
        daysAgo,
        daysRemaining: Math.max(0, graceDays - daysAgo),
      });
    }
  }
  return { expired, inGrace };
}

const EMPTY_ANALYSIS: ConfigPruneAnalysis = {
  staleCerts: [],
  expiredArchives: [],
  graceArchives: [],
  droppedRefs: [],
  warnings: [],
  orphanRepos: [],
  orphanStateRepos: [],
  goneMachineRepos: [],
  goneMachineState: [],
};

/** Any bucket flag (`--certs-only`, `--archives-only`, `--refs-only`, `--gone-machine-repos`) narrows the run to the buckets named; no bucket flag prunes every bucket. `--gone-machine-repos` selects no cert, archive or ref bucket, so with it alone the run touches only the gone-machine repos and their state. */
function selectBuckets(options: ConfigPruneOptions): {
  wantCerts: boolean;
  wantArchives: boolean;
  wantRefs: boolean;
} {
  const narrowed = [
    options.certsOnly,
    options.archivesOnly,
    options.refsOnly,
    options.goneMachineRepos,
  ].some(Boolean);
  return {
    wantCerts: !narrowed || Boolean(options.certsOnly),
    wantArchives: !narrowed || Boolean(options.archivesOnly),
    wantRefs: !narrowed || Boolean(options.refsOnly),
  };
}

/**
 * The one prune pass, run on `cfg` in place by both the dry run (on a clone) and the apply (inside
 * `updateSyncedConfig`, so a replay after a version conflict re-runs it on the fresh server copy).
 */
function prunePass(cfg: RdcConfig, options: ConfigPruneOptions): ConfigPruneAnalysis {
  const { wantCerts, wantArchives, wantRefs } = selectBuckets(options);
  const graceDays = options.graceDays ?? cfg.defaults?.pruneGraceDays ?? DEFAULT_GRACE_DAYS;

  // Archives FIRST so the cert anchors below are computed against the post-prune resource set; otherwise certs whose anchor is in expiredArchives would be classified as live and survive the run.
  const arch = wantArchives
    ? mutateAndExtractArchives(cfg, graceDays, Boolean(options.purgeArchived))
    : { expired: [] as ArchivedRepository[], inGrace: [] as ArchiveGraceEntry[] };

  const goneMachineRepos = findGoneMachineRepos(cfg);
  if (options.goneMachineRepos) archiveGoneMachineRepos(cfg, goneMachineRepos);
  const goneMachineState = wantRefs || options.goneMachineRepos ? pruneGoneMachineState(cfg) : [];

  const staleCerts = wantCerts ? pruneCertCacheBuckets(cfg, buildConfigAnchors(cfg)) : [];
  const refs = wantRefs
    ? pruneDanglingRefs(cfg)
    : { dropped: [] as DroppedRef[], warnings: [] as string[] };

  // Reported whichever bucket filter is active: an orphan repo entry is worth surfacing even when the operator asked for a narrower run, because it is the one leftover that silently carries secrets.
  const orphanRepos = findOrphanRepos(cfg);
  if (options.orphanRepos) removeOrphanRepos(cfg, orphanRepos);
  // Runs after removal so entries dropped above have their state records collected in the same pass rather than needing a second invocation.
  const orphanStateRepos = pruneOrphanStateRepos(cfg);

  return {
    staleCerts,
    expiredArchives: arch.expired,
    graceArchives: arch.inGrace,
    droppedRefs: refs.dropped,
    warnings: refs.warnings,
    orphanRepos,
    orphanStateRepos,
    goneMachineRepos,
    goneMachineState,
  };
}

/**
 * Compute the prune analysis without writing anything. Safe to call any
 * number of times.
 */
export async function analyzeConfigPrune(
  options: ConfigPruneOptions = {}
): Promise<ConfigPruneAnalysis> {
  const config = await configService.getCurrent();
  if (!config) return structuredClone(EMPTY_ANALYSIS);
  // Deep-clone so the analysis pass leaves the in-memory config untouched.
  return prunePass(JSON.parse(JSON.stringify(config)) as RdcConfig, options);
}

/**
 * Repository entries that name no machine.
 *
 * Placement is the config's record of which machine holds a repo's image. An
 * entry with none is either genuinely dead (the repo was deleted elsewhere) or
 * simply never reconciled. This check cannot tell those apart on its own ,
 * `config prune` is a local-only command and does not reach out to machines ,
 * so the caller reports the list and points at `config reconcile`, which does
 * the machine-side scan, before offering to remove anything.
 */
export function findOrphanRepos(cfg: RdcConfig): OrphanRepoEntry[] {
  const repos = cfg.resources?.repositories ?? {};
  const orphans: OrphanRepoEntry[] = [];

  for (const [name, repo] of Object.entries(repos)) {
    // Placement is a union: a repo may be pinned to a machine OR to a datastore. Only an entry with neither is unplaced, treating a datastore-placed repo as an orphan would delete a live repo's secrets.
    const placement = repo.placement;
    const placed =
      placement !== undefined &&
      (('machine' in placement && Boolean(placement.machine)) ||
        ('datastore' in placement && Boolean(placement.datastore)));
    if (placed) continue;

    const grandTag = repo.grand ? repo.tags[repo.grand] : undefined;
    orphans.push({ name, guid: grandTag?.repositoryGuid });
  }

  return orphans;
}

/**
 * Remove the given repository entries from `cfg` in-place.
 *
 * Also drops the matching `state.repos.<name>` runtime record. Per-repo runtime
 * status lives there rather than on the resource entry, and nothing else prunes
 * it, leaving it behind strands that repo's `networkId` in the allocation
 * space, so a later repo create can believe an ID is taken when no repo owns it.
 */
function removeOrphanRepos(cfg: RdcConfig, orphans: OrphanRepoEntry[]): void {
  const repos = cfg.resources?.repositories;
  const stateRepos = cfg.state?.repos;

  for (const { name } of orphans) {
    if (repos) delete repos[name];
    if (stateRepos) delete stateRepos[name];
  }
}

/**
 * Drop `state.repos` records that no repository entry owns, returning their
 * names.
 *
 * These are left behind whenever a repository entry is removed, by this
 * command's own --orphan-repos pass, or by any earlier hand-edit. Nothing else
 * collects them, and each one strands a `networkId` in the allocation space
 * that no live repo owns.
 */
export function pruneOrphanStateRepos(cfg: RdcConfig): OrphanStateRepo[] {
  const stateRepos = cfg.state?.repos;
  if (!stateRepos) return [];

  const live = new Set(Object.keys(cfg.resources?.repositories ?? {}));
  const dropped: OrphanStateRepo[] = [];

  for (const name of Object.keys(stateRepos)) {
    if (live.has(name)) continue;
    delete stateRepos[name];
    dropped.push(name);
  }

  return dropped;
}

/**
 * Move every tag of each listed family into `resources.deletedRepositories` (the same record
 * `repo delete --archive-config` writes), and drop the family and its `state.repos` runtime.
 */
function archiveGoneMachineRepos(cfg: RdcConfig, gone: GoneMachineRepo[]): void {
  const families = cfg.resources?.repositories;
  if (!cfg.resources || !families || gone.length === 0) return;
  const flat = flattenRepositories(families, cfg.state?.repos);
  const archived = [...(cfg.resources.deletedRepositories ?? [])];
  for (const { name } of gone) {
    const keys = Object.keys(families[name]?.tags ?? {}).map((tag) => `${name}:${tag}`);
    archived.push(
      ...keys.filter((key) => key in flat).map((key) => buildArchivedRecord(key, flat[key]))
    );
    delete families[name];
    if (cfg.state?.repos) delete cfg.state.repos[name];
  }
  cfg.resources.deletedRepositories = archived;
}

/**
 * Drop runtime records keyed by a machine the config no longer has: `state.licenseRefresh.<m>`
 * (the licence-refresh rate limit) and `state.repos.<repo>.<tag>.pushState.<m>` (the push record
 * `repo delete` reads as "another machine holds a copy"). Runtime only, no secrets: dropped
 * unconditionally. Returns the dropped paths.
 */
function pruneGoneMachineState(cfg: RdcConfig): string[] {
  const state = cfg.state;
  if (!state) return [];
  return [...pruneGoneLicenseRefresh(cfg, state), ...pruneGonePushState(cfg, state)];
}

type PruneState = NonNullable<RdcConfig['state']>;

/** Drop `state.licenseRefresh.<m>` for every machine the config no longer has. */
function pruneGoneLicenseRefresh(cfg: RdcConfig, state: PruneState): string[] {
  const refresh = state.licenseRefresh;
  if (!refresh) return [];
  const gone = Object.keys(refresh).filter((machine) => !machineExists(cfg, machine));
  for (const machine of gone) delete refresh[machine];
  if (Object.keys(refresh).length === 0) delete state.licenseRefresh;
  return gone.map((machine) => `state.licenseRefresh.${machine}`);
}

/** Drop `state.repos.<repo>.<tag>.pushState.<m>` for every machine the config no longer has. */
function pruneGonePushState(cfg: RdcConfig, state: PruneState): string[] {
  const dropped: string[] = [];
  for (const [repo, tags] of Object.entries(state.repos ?? {})) {
    for (const [tag, runtime] of Object.entries(tags)) {
      const prefix = `state.repos.${repo}.${tag}.pushState`;
      dropped.push(...dropGonePushEntries(cfg, runtime, prefix));
    }
  }
  return dropped;
}

type RepoRuntimeRecord = NonNullable<PruneState['repos']>[string][string];

/** Drop one runtime record's pushState entries for gone machines; returns their paths. */
function dropGonePushEntries(cfg: RdcConfig, runtime: RepoRuntimeRecord, prefix: string): string[] {
  const push = runtime.pushState;
  if (!push) return [];
  const gone = Object.keys(push).filter((machine) => !machineExists(cfg, machine));
  for (const machine of gone) delete push[machine];
  if (gone.length > 0 && Object.keys(push).length === 0) delete runtime.pushState;
  return gone.map((machine) => `${prefix}.${machine}`);
}

/** Classify and remove expired archives from `cfg` in-place; return both lists. */
function mutateAndExtractArchives(
  cfg: RdcConfig,
  graceDays: number,
  purgeAll: boolean
): { expired: ArchivedRepository[]; inGrace: ArchiveGraceEntry[] } {
  const all = cfg.resources?.deletedRepositories ?? [];
  const cls = purgeAll
    ? { expired: all, inGrace: [] as ArchiveGraceEntry[] }
    : classifyArchives(all, graceDays);
  if (cfg.resources && cls.expired.length > 0) {
    const expiredGuids = new Set(cls.expired.map((e) => e.repositoryGuid));
    cfg.resources.deletedRepositories = all.filter((a) => !expiredGuids.has(a.repositoryGuid));
    if (cfg.resources.deletedRepositories.length === 0) {
      delete cfg.resources.deletedRepositories;
    }
  }
  return cls;
}

/**
 * Apply the prune. Writes the cleaned config atomically via
 * `updateSyncedConfig` (pushed for a remote config; a replay after a version conflict
 * re-runs the analysis against the fresh server copy). Returns the same analysis the dry-run path
 * produces, callers can render either path identically.
 */
export async function applyConfigPrune(
  options: ConfigPruneOptions = {}
): Promise<ConfigPruneAnalysis> {
  let analysis = structuredClone(EMPTY_ANALYSIS);
  await updateSyncedConfig(configService.getEffectiveConfigName(), (cfg) => {
    analysis = prunePass(cfg, options);
    return cfg;
  });
  return analysis;
}
