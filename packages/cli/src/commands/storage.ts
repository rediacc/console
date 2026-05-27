import {
  formatSizeBytes,
  type RemoteFile,
  resolveGuidFileNames,
} from '@rediacc/shared/queue-vault';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { storageBrowserService } from '../services/storage-browser.js';
import { createResourceCommands } from '../utils/commandFactory.js';
import { handleError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import { assertStorageExists } from './_validate.js';
import { parseRepositoryListOutput } from './repo-list-parser.js';

function formatFileName(f: RemoteFile): string {
  if (f.isDirectory) return `${f.name}/`;
  if (f.isGuid && f.originalGuid && f.name !== f.originalGuid) return f.name;
  if (f.isGuid) return `[backup] ${f.name}`;
  return f.name;
}

function formatFileType(f: RemoteFile): string {
  if (f.isDirectory) return 'dir';
  if (f.isGuid) return 'backup';
  return 'file';
}

interface StoragePruneOptions {
  machine: string;
  dryRun?: boolean;
  force?: boolean;
  forceDeleteMounted?: boolean;
  graceDays?: number;
  debug?: boolean;
  skipRouterRestart?: boolean;
}

/** Build a set of GUIDs that are currently live (mounted or running) on the
 *  machine. Used as a safety preflight before deleting cloud backups. */
async function fetchLiveGuids(options: StoragePruneOptions): Promise<Set<string>> {
  const result = await localExecutorService.execute({
    functionName: 'repository_list',
    machineName: options.machine,
    params: {},
    debug: options.debug,
    captureOutput: true,
    skipRouterRestart: options.skipRouterRestart,
  });
  if (!result.success) {
    // Probe failure is non-fatal — surface it but don't block the operator;
    // the delete loop still has the analyzePrune protections.
    outputService.warn(`Could not list machine repositories for safety check: ${result.error}`);
    return new Set();
  }
  const repos = parseRepositoryListOutput(result.stdout ?? '[]') as {
    name?: string;
    guid?: string;
    mounted?: boolean;
    docker_running?: boolean;
  }[];
  const live = new Set<string>();
  for (const r of repos) {
    if (r.mounted || r.docker_running) {
      const guid = r.guid ?? r.name;
      if (typeof guid === 'string') live.add(guid);
    }
  }
  return live;
}

/** Parse backup GUIDs from executor output. */
function parseBackupGuids(stdout: string): string[] {
  const rawOutput = stdout
    .split('\n')
    .map((line) => line.replace(/^\[.*?\]\s*/, ''))
    .join('\n');
  const jsonMatch = /\{[\s\S]*\}/.exec(rawOutput);
  const parsed = jsonMatch
    ? (JSON.parse(jsonMatch[0]) as {
        entries?: { name: string; isDirectory: boolean }[];
      })
    : { entries: [] };
  return (parsed.entries ?? []).filter((e) => !e.isDirectory).map((e) => e.name);
}

/** Storage layout — scheduled backups split into these subpaths. */
const STORAGE_MODES = ['hot', 'cold'] as const;
type StorageMode = (typeof STORAGE_MODES)[number];

/** List GUIDs under one subpath. Returns empty when the subpath is
 *  legitimately missing (a fresh storage that hasn't seen the cold/ tier
 *  yet, for example) but throws on real failures so a broken SSH/renet/
 *  storage path can't be silently treated as "no backups, nothing to do".
 *  The previous swallow-all-errors behavior was a P1 hazard: it could leave
 *  orphans in place while reporting success. */
async function listGuidsAtPath(
  storageName: string,
  subpath: StorageMode,
  options: StoragePruneOptions
): Promise<string[]> {
  const result = await localExecutorService.execute({
    functionName: 'backup_list',
    machineName: options.machine,
    params: { sourceType: 'storage', from: storageName, path: subpath },
    debug: options.debug,
    captureOutput: true,
    skipRouterRestart: options.skipRouterRestart,
  });
  if (!result.success) {
    const stderr = (result.error ?? '').toString();
    // rclone reports a missing remote subpath as "directory not found".
    // Anything else is a real error — surface it.
    if (/(directory not found|no such (file|directory))/i.test(stderr)) {
      return [];
    }
    const reason = result.error ?? (stderr.length > 0 ? stderr : 'no error message captured');
    throw new Error(`backup_list failed for ${storageName}/${subpath}: ${reason}`);
  }
  return parseBackupGuids(result.stdout ?? '');
}

async function collectGuidsByMode(
  storageName: string,
  options: StoragePruneOptions
): Promise<{ remoteGuids: string[]; guidLocations: Map<string, StorageMode[]> }> {
  const perMode = await Promise.all(
    STORAGE_MODES.map(async (mode) => ({
      mode,
      guids: await listGuidsAtPath(storageName, mode, options),
    }))
  );
  const guidLocations = new Map<string, StorageMode[]>();
  for (const { mode, guids } of perMode) {
    for (const guid of guids) {
      const existing = guidLocations.get(guid) ?? [];
      existing.push(mode);
      guidLocations.set(guid, existing);
    }
  }
  return { remoteGuids: [...guidLocations.keys()], guidLocations };
}

async function applyMountSafety<T extends { guid: string }>(
  orphans: T[],
  options: StoragePruneOptions
): Promise<T[]> {
  if (orphans.length === 0) return orphans;
  const liveGuids = await fetchLiveGuids(options);
  const mounted = orphans.filter((o) => liveGuids.has(o.guid));
  if (mounted.length === 0) return orphans;
  if (options.forceDeleteMounted) {
    outputService.warn(
      `--force-delete-mounted: proceeding with ${mounted.length} mounted/running orphan(s)`
    );
    return orphans;
  }
  for (const m of mounted) {
    outputService.warn(
      `Skipping ${m.guid.slice(0, 8)}…: currently mounted or running on "${options.machine}". Pass --force-delete-mounted to override.`
    );
  }
  const mountedSet = new Set(mounted.map((m) => m.guid));
  return orphans.filter((o) => !mountedSet.has(o.guid));
}

function partitionOrphansByMode<T extends { guid: string }>(
  orphans: T[],
  guidLocations: Map<string, StorageMode[]>
): Map<StorageMode, string[]> {
  const orphanGuids = new Set(orphans.map((o) => o.guid));
  const byMode = new Map<StorageMode, string[]>();
  for (const guid of orphanGuids) {
    for (const mode of guidLocations.get(guid) ?? []) {
      const list = byMode.get(mode) ?? [];
      list.push(guid);
      byMode.set(mode, list);
    }
  }
  return byMode;
}

async function deleteOrphansByMode(
  byMode: Map<StorageMode, string[]>,
  storageName: string,
  options: StoragePruneOptions
): Promise<void> {
  let firstCall = true;
  for (const [mode, guids] of byMode) {
    outputService.info(`Deleting ${guids.length} orphan(s) from ${mode}/`);
    const deleteResult = await localExecutorService.execute({
      functionName: 'backup_delete',
      machineName: options.machine,
      params: {
        repository: guids[0],
        repositories: guids.join(','),
        sourceType: 'storage',
        from: storageName,
        path: mode,
      },
      debug: options.debug,
      skipRouterRestart: options.skipRouterRestart,
      quietSpinners: !firstCall,
    });
    firstCall = false;
    if (!deleteResult.success) {
      outputService.error(
        `Failed to delete from ${mode}/: ${deleteResult.error} (${guids.length} GUID(s) attempted)`
      );
    }
  }
}

async function executeStoragePrune(
  storageName: string,
  options: StoragePruneOptions
): Promise<void> {
  const { analyzePrune, printPruneAnalysis, purgeExpiredArchives } = await import(
    '../services/prune.js'
  );

  outputService.info(t('commands.storage.prune.listing', { storage: storageName }));
  const { remoteGuids, guidLocations } = await collectGuidsByMode(storageName, options);

  if (remoteGuids.length === 0) {
    outputService.info(t('commands.storage.prune.noBackups'));
    return;
  }

  outputService.info(t('commands.storage.prune.found', { count: remoteGuids.length }));

  const analysis = await analyzePrune(remoteGuids, {
    force: options.force,
    graceDays: options.graceDays,
  });

  const orphansToDelete = await applyMountSafety(analysis.orphaned, options);
  printPruneAnalysis({ ...analysis, orphaned: orphansToDelete }, Boolean(options.dryRun));

  if (!options.dryRun && orphansToDelete.length > 0) {
    const byMode = partitionOrphansByMode(orphansToDelete, guidLocations);
    await deleteOrphansByMode(byMode, storageName, options);
    outputService.success(t('commands.storage.prune.completed', { count: orphansToDelete.length }));
  }

  await purgeExpiredArchives(options.graceDays);
}

export function registerStorageCommands(program: Command): void {
  const storage = createResourceCommands(program, {
    resourceName: 'storage',
    resourceNamePlural: 'storage systems',
    nameField: 'storageName',
    parentOption: 'team',
    operations: {
      list: async (params) => {
        const provider = await getStateProvider();
        return provider.storage.list({ teamName: params?.teamName as string });
      },
      create: async (payload) => {
        const provider = await getStateProvider();
        return provider.storage.create(payload);
      },
      rename: async (payload) => {
        const provider = await getStateProvider();
        return provider.storage.rename(payload);
      },
      delete: async (payload) => {
        const provider = await getStateProvider();
        return provider.storage.delete(payload);
      },
    },
    transformCreatePayload: (name, opts) => ({
      storageName: name,
      teamName: opts.team,
    }),
    vaultConfig: {
      fetch: async (params) => {
        const provider = await getStateProvider();
        return provider.storage.getVault(params) as Promise<never>;
      },
      vaultType: 'Storage',
    },
    vaultUpdateConfig: {
      update: async (payload) => {
        const provider = await getStateProvider();
        return provider.storage.updateVault(payload);
      },
      vaultFieldName: 'vaultContent',
    },
  });
  storage.summary(t('commands.storage.descriptionShort'));

  // Add browse subcommand for listing files in a storage system
  storage
    .command('browse')
    .description(t('commands.storage.browse.description'))
    .requiredOption('--name <name>', t('options.name'))
    .option('--path <subpath>', t('commands.storage.browse.pathOption'), '')
    .action(async (options: { name: string; path: string }) => {
      try {
        const name = options.name;
        const storageConfig = await configService.getStorage(name);
        const guidMap = await configService.getRepositoryGuidMap();

        let files = await withSpinner(t('commands.storage.browse.listing', { name }), () =>
          storageBrowserService.browse(storageConfig.vaultContent, options.path || undefined)
        );

        files = resolveGuidFileNames(files, guidMap);

        if (files.length === 0) {
          outputService.info(t('commands.storage.browse.noFiles'));
          return;
        }

        const tableData = files.map((f) => ({
          name: formatFileName(f),
          type: formatFileType(f),
          size: f.isDirectory ? '-' : formatSizeBytes(f.size),
          modified: f.modTime ?? '-',
        }));

        outputService.print(tableData);
        outputService.info(`\n${files.length} entries`);
      } catch (error) {
        handleError(error);
      }
    });

  // storage prune <storageName> — remove orphaned backups from storage
  storage
    .command('prune')
    .summary(t('commands.storage.prune.descriptionShort'))
    .description(t('commands.storage.prune.description'))
    .requiredOption('--name <name>', t('options.name'))
    .requiredOption('-m, --machine <name>', t('commands.storage.prune.machineOption'))
    .option('--dry-run', t('options.dryRun'))
    .option('--force', t('options.force'))
    .option('--force-delete-mounted', t('commands.storage.prune.forceDeleteMountedOption'))
    .option('--grace-days <days>', t('options.graceDays'), Number.parseInt)
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (options: StoragePruneOptions & { name: string }) => {
      try {
        const storageName = options.name;
        await assertStorageExists(storageName);
        await executeStoragePrune(storageName, options);
      } catch (error) {
        handleError(error);
      }
    });
}
