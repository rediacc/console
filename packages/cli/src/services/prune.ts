/**
 * Prune Analysis Service
 *
 * Shared logic for storage prune and machine prune --orphaned-repos.
 * Compares remote GUIDs against all config files to identify orphaned entries.
 */

import { configFileStorage } from '../adapters/config-file-storage.js';
import { t } from '../i18n/index.js';
import type { ArchivedRepository, RdcConfig } from '../types/index.js';
import { configService } from './config-resources.js';
import { outputService } from './output.js';

const DEFAULT_GRACE_DAYS = 7;

export interface PruneCandidate {
  guid: string;
  reason: string;
}

export interface PruneAnalysis {
  /** GUIDs that will be deleted (not in any config, past grace period) */
  orphaned: PruneCandidate[];
  /** GUIDs that are protected (in a config or within grace period) */
  protected: PruneCandidate[];
}

interface AnalyzeOptions {
  force?: boolean;
  graceDays?: number;
}

interface ConfigScanResult {
  guidSources: Map<string, string[]>;
  unreadableConfigs: string[];
}

/** Add a GUID → config-name entry to the sources map. */
function addGuidSource(guidSources: Map<string, string[]>, guid: string, configName: string): void {
  const sources = guidSources.get(guid) ?? [];
  sources.push(configName);
  guidSources.set(guid, sources);
}

/** Scan the current config for repository GUIDs via configService. */
async function scanCurrentConfig(
  guidSources: Map<string, string[]>,
  currentConfigName: string
): Promise<void> {
  try {
    const repos = await configService.listRepositories();
    for (const r of repos) {
      const guid = r.config.repositoryGuid;
      if (guid) addGuidSource(guidSources, guid, currentConfigName);
    }
  } catch {
    // Current config unreadable — shouldn't happen but handle gracefully
  }
}

/** Scan a single non-current config file for repository GUIDs. */
async function scanOtherConfig(
  guidSources: Map<string, string[]>,
  unreadableConfigs: string[],
  name: string
): Promise<void> {
  try {
    const config = await configFileStorage.load(name);

    // Check if config is encrypted and repos aren't readable
    if (config.encrypted && !config.repositories) {
      unreadableConfigs.push(name);
      return;
    }

    const repos = config.repositories ?? {};
    for (const repoConfig of Object.values(repos)) {
      const guid = repoConfig.repositoryGuid;
      if (guid) addGuidSource(guidSources, guid, name);
    }
  } catch {
    unreadableConfigs.push(name);
  }
}

/**
 * Scan all config files and collect every referenced repository GUID.
 * Returns a map of GUID -> list of config names that reference it,
 * plus a list of configs that couldn't be fully read (encrypted without password).
 *
 * For the current config: uses configService (handles encryption + S3 transparently).
 * For other configs: reads raw JSON. If encrypted (has encryptedResources but no readable
 * repositories), marks as unreadable -- prune will refuse to delete unless --force.
 */
async function collectAllConfigGuids(): Promise<ConfigScanResult> {
  const guidSources = new Map<string, string[]>();
  const unreadableConfigs: string[] = [];
  const currentConfigName = configService.getCurrentName();

  await scanCurrentConfig(guidSources, currentConfigName);

  const configNames = await configFileStorage.list();
  for (const name of configNames) {
    if (name === currentConfigName) continue;
    await scanOtherConfig(guidSources, unreadableConfigs, name);
  }

  return { guidSources, unreadableConfigs };
}

/**
 * Collect archived repos with their deletedAt timestamps from the current config.
 */
async function collectArchivedGuids(): Promise<Map<string, Date>> {
  const archived = new Map<string, Date>();
  try {
    const repos = await configService.listArchivedRepositories();
    for (const repo of repos) {
      if (repo.repositoryGuid && repo.deletedAt) {
        archived.set(repo.repositoryGuid, new Date(repo.deletedAt));
      }
    }
  } catch {
    // No archived repos or can't read
  }
  return archived;
}

/** Resolve the grace-day threshold from options or config. */
function resolveGraceDays(options: AnalyzeOptions, config: RdcConfig | null): number {
  return options.graceDays ?? config?.pruneGraceDays ?? DEFAULT_GRACE_DAYS;
}

/** Classify a single GUID as orphaned or protected. */
function classifyGuid(
  guid: string,
  allConfigGuids: Map<string, string[]>,
  archivedGuids: Map<string, Date>,
  currentConfigName: string,
  cutoff: Date,
  graceDays: number,
  force: boolean
): PruneCandidate & { isOrphaned: boolean } {
  const sources = allConfigGuids.get(guid);

  // Check 1: In current config?
  if (sources?.includes(currentConfigName)) {
    return { guid, reason: `active in ${currentConfigName}`, isOrphaned: false };
  }

  // Check 2: In another config?
  if (sources && sources.length > 0 && !force) {
    return {
      guid,
      reason: `exists in ${sources.join(', ')} (use --force to override)`,
      isOrphaned: false,
    };
  }

  // Check 3: Recently archived (within grace period)?
  const archivedAt = archivedGuids.get(guid);
  if (archivedAt && archivedAt > cutoff && !force) {
    const daysAgo = Math.floor((Date.now() - archivedAt.getTime()) / 86400000);
    return {
      guid,
      reason: `archived ${daysAgo}d ago (grace period: ${graceDays}d, use --force to override)`,
      isOrphaned: false,
    };
  }

  // Orphaned — safe to delete
  return {
    guid,
    reason: sources?.length ? `forced (in ${sources.join(', ')})` : 'not in any config',
    isOrphaned: true,
  };
}

/**
 * Analyze which remote GUIDs are orphaned vs protected.
 *
 * Safety model:
 * 1. In current config's active repos -> protected (keep)
 * 2. In another config's repos -> protected unless --force
 * 3. In archivedRepositories within grace period -> protected unless --force
 * 4. Otherwise -> orphaned (delete)
 */
export async function analyzePrune(
  remoteGuids: string[],
  options: AnalyzeOptions = {}
): Promise<PruneAnalysis> {
  const config = await configService.getCurrent();
  const graceDays = resolveGraceDays(options, config);
  const cutoff = new Date(Date.now() - graceDays * 86400000);
  const currentConfigName = configService.getCurrentName();

  const { guidSources: allConfigGuids, unreadableConfigs } = await collectAllConfigGuids();
  const archivedGuids = await collectArchivedGuids();

  // Warn about unreadable configs — block deletion unless --force
  if (unreadableConfigs.length > 0) {
    outputService.warn(
      t('services.prune.unreadableConfigs', {
        count: unreadableConfigs.length,
        names: unreadableConfigs.join(', '),
      })
    );
    if (!options.force) {
      outputService.warn(t('services.prune.refusingPrune'));
      return { orphaned: [], protected: [] };
    }
  }

  const orphaned: PruneCandidate[] = [];
  const protectedItems: PruneCandidate[] = [];

  for (const guid of remoteGuids) {
    const result = classifyGuid(
      guid,
      allConfigGuids,
      archivedGuids,
      currentConfigName,
      cutoff,
      graceDays,
      options.force ?? false
    );
    const { isOrphaned, ...candidate } = result;
    if (isOrphaned) {
      orphaned.push(candidate);
    } else {
      protectedItems.push(candidate);
    }
  }

  return { orphaned, protected: protectedItems };
}

/**
 * Print prune analysis results.
 */
export function printPruneAnalysis(analysis: PruneAnalysis, dryRun: boolean): void {
  if (analysis.protected.length > 0) {
    outputService.info(`Protected (${analysis.protected.length}):`);
    for (const item of analysis.protected) {
      outputService.info(`  ${item.guid.slice(0, 8)}… — ${item.reason}`);
    }
  }

  if (analysis.orphaned.length > 0) {
    outputService.info(`\nOrphaned (${analysis.orphaned.length}):`);
    for (const item of analysis.orphaned) {
      outputService.info(`  ${item.guid.slice(0, 8)}… — ${item.reason}`);
    }
  }

  if (analysis.orphaned.length === 0) {
    outputService.success(t('services.prune.noOrphaned'));
  } else if (dryRun) {
    outputService.warn(`\nDry run: ${analysis.orphaned.length} entries would be deleted`);
  }
}

/**
 * Purge archived repositories older than the grace period.
 * Returns the list of purged entries.
 */
export async function purgeExpiredArchives(graceDays?: number): Promise<ArchivedRepository[]> {
  const config = await configService.getCurrent();
  const threshold = graceDays ?? config?.pruneGraceDays ?? DEFAULT_GRACE_DAYS;

  const expired = await configService.purgeExpiredArchives(threshold);
  if (expired.length > 0) {
    outputService.info(`Purged ${expired.length} expired archived repositories`);
  }

  return expired;
}
