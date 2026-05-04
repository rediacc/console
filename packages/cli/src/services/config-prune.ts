/**
 * `rdc config prune` — sweep stale leftovers from the local config file.
 *
 * Three buckets, all pure-local (no SSH/renet):
 *
 *   1. ACME cert-cache entries whose anchor (GUID / repo name / machine)
 *      is no longer in the active config.
 *   2. Expired archived repositories — `resources.deletedRepositories[]`
 *      entries whose `deletedAt` is older than `defaults.pruneGraceDays`
 *      (default 7). In-grace entries are kept for accidental-delete
 *      recovery.
 *   3. Dangling cross-references (machine→strategy, strategy→repo).
 *
 * Exposes `analyzeConfigPrune(options)` for preview + `applyConfigPrune`
 * for the real run. The analysis return shape feeds directly into the CLI
 * formatter so command-layer code stays thin.
 */

import { gunzipSync, gzipSync } from 'node:zlib';
import { configFileStorage } from '../adapters/config-file-storage.js';
import type { ArchivedRepository, RdcConfig } from '../schema/schemas.js';
import { parseRepoRef } from '../utils/config-schema.js';
import { configService } from './config-resources.js';
import { type ConfigAnchors, pruneCertsByAnchor } from './cert-cache.js';
import { pruneDanglingRefs, type DroppedRef } from './config-refs-prune.js';

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
  /** Archived repos still in grace — kept, listed for visibility. */
  graceArchives: ArchiveGraceEntry[];
  /** Cross-reference values that would be (or were) dropped. */
  droppedRefs: DroppedRef[];
  /** Soft warnings (storage destination references — flagged, not auto-removed). */
  warnings: string[];
}

/**
 * Build the set of live anchors from the active config. Archived repos are
 * intentionally treated as live so their certs survive the grace window —
 * an operator restoring an archive shouldn't have to re-issue certs.
 *
 * Exported for test access; the apply path also uses it via the closure.
 */
export function buildConfigAnchors(config: RdcConfig): ConfigAnchors {
  const guids = new Set<string>();
  const repoNames = new Set<string>();
  const machines = new Set<string>();

  for (const [name, repo] of Object.entries(config.resources?.repositories ?? {})) {
    if (repo.repositoryGuid) guids.add(repo.repositoryGuid);
    repoNames.add(parseRepoRef(name).name);
  }
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
  const cache = config.infra?.acmeCertCache;
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

/**
 * Compute the prune analysis without writing anything. Safe to call any
 * number of times.
 */
export async function analyzeConfigPrune(
  options: ConfigPruneOptions = {}
): Promise<ConfigPruneAnalysis> {
  const config = await configService.getCurrent();
  if (!config) {
    return {
      staleCerts: [],
      expiredArchives: [],
      graceArchives: [],
      droppedRefs: [],
      warnings: [],
    };
  }

  const wantCerts = !options.archivesOnly && !options.refsOnly;
  const wantArchives = !options.certsOnly && !options.refsOnly;
  const wantRefs = !options.certsOnly && !options.archivesOnly;

  // Deep-clone so the analysis pass leaves the in-memory config untouched —
  // the apply path re-runs the same logic via `configFileStorage.update`.
  const clone = JSON.parse(JSON.stringify(config)) as RdcConfig;
  const graceDays = options.graceDays ?? clone.defaults?.pruneGraceDays ?? DEFAULT_GRACE_DAYS;

  // Apply archive removal to the clone FIRST so cert anchors are computed
  // against the post-prune resource set; otherwise certs whose anchor is in
  // expiredArchives would be classified as live and survive the run.
  const arch = wantArchives
    ? mutateAndExtractArchives(clone, graceDays, Boolean(options.purgeArchived))
    : { expired: [] as ArchivedRepository[], inGrace: [] as ArchiveGraceEntry[] };

  const anchors = buildConfigAnchors(clone);
  const staleCerts = wantCerts ? pruneCertCacheBuckets(clone, anchors) : [];
  const refs = wantRefs
    ? pruneDanglingRefs(clone)
    : { dropped: [] as DroppedRef[], warnings: [] as string[] };

  return {
    staleCerts,
    expiredArchives: arch.expired,
    graceArchives: arch.inGrace,
    droppedRefs: refs.dropped,
    warnings: refs.warnings,
  };
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
 * `configFileStorage.update`. Returns the same analysis the dry-run path
 * produces — callers can render either path identically.
 */
export async function applyConfigPrune(
  options: ConfigPruneOptions = {}
): Promise<ConfigPruneAnalysis> {
  const configName = configService.getEffectiveConfigName();

  const wantCerts = !options.archivesOnly && !options.refsOnly;
  const wantArchives = !options.certsOnly && !options.refsOnly;
  const wantRefs = !options.certsOnly && !options.archivesOnly;

  let analysis: ConfigPruneAnalysis = {
    staleCerts: [],
    expiredArchives: [],
    graceArchives: [],
    droppedRefs: [],
    warnings: [],
  };

  await configFileStorage.update(configName, (cfg) => {
    const graceDays = options.graceDays ?? cfg.defaults?.pruneGraceDays ?? DEFAULT_GRACE_DAYS;

    // Prune archives FIRST so the cert-anchor pass below sees the post-prune
    // resource set. If we built anchors from the pre-prune config, certs
    // anchored to repositories about to be purged would survive the run as
    // "live" and need a second invocation to be removed.
    const arch = wantArchives
      ? mutateAndExtractArchives(cfg, graceDays, Boolean(options.purgeArchived))
      : { expired: [] as ArchivedRepository[], inGrace: [] as ArchiveGraceEntry[] };
    const anchors = buildConfigAnchors(cfg);
    const staleCerts = wantCerts ? pruneCertCacheBuckets(cfg, anchors) : [];
    const refs = wantRefs
      ? pruneDanglingRefs(cfg)
      : { dropped: [] as DroppedRef[], warnings: [] as string[] };

    analysis = {
      staleCerts,
      expiredArchives: arch.expired,
      graceArchives: arch.inGrace,
      droppedRefs: refs.dropped,
      warnings: refs.warnings,
    };
    return cfg;
  });

  return analysis;
}
