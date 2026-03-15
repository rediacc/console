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
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { withSpinner } from '../utils/spinner.js';

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
  graceDays?: number;
  debug?: boolean;
  skipRouterRestart?: boolean;
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

/** Execute the storage prune workflow. */
async function executeStoragePrune(
  storageName: string,
  options: StoragePruneOptions
): Promise<void> {
  const { analyzePrune, printPruneAnalysis, purgeExpiredArchives } = await import(
    '../services/prune.js'
  );

  // List backups in storage via renet
  outputService.info(t('commands.storage.prune.listing', { storage: storageName }));
  const listResult = await localExecutorService.execute({
    functionName: 'backup_list',
    machineName: options.machine,
    params: { sourceType: 'storage', from: storageName },
    debug: options.debug,
    captureOutput: true,
    skipRouterRestart: options.skipRouterRestart,
  });

  if (!listResult.success) {
    renderLocalExecutionFailure(listResult, t('commands.storage.prune.listFailed'));
    return;
  }

  const remoteGuids = parseBackupGuids(listResult.stdout ?? '');

  if (remoteGuids.length === 0) {
    outputService.info(t('commands.storage.prune.noBackups'));
    return;
  }

  outputService.info(t('commands.storage.prune.found', { count: remoteGuids.length }));

  // Analyze
  const analysis = await analyzePrune(remoteGuids, {
    force: options.force,
    graceDays: options.graceDays,
  });
  printPruneAnalysis(analysis, options.dryRun ?? true);

  // Delete orphaned backups
  if (!options.dryRun && analysis.orphaned.length > 0) {
    for (const item of analysis.orphaned) {
      outputService.info(`Deleting ${item.guid.slice(0, 8)}…`);
      const deleteResult = await localExecutorService.execute({
        functionName: 'backup_delete',
        machineName: options.machine,
        params: {
          repository: item.guid,
          sourceType: 'storage',
          from: storageName,
        },
        debug: options.debug,
        skipRouterRestart: options.skipRouterRestart,
      });
      if (!deleteResult.success) {
        outputService.error(`Failed to delete ${item.guid}: ${deleteResult.error}`);
      }
    }
    outputService.success(
      t('commands.storage.prune.completed', {
        count: analysis.orphaned.length,
      })
    );
  }

  // Auto-purge expired archives
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

  // Add browse subcommand for listing files in a storage system
  storage
    .command('browse <name>')
    .description(t('commands.storage.browse.description'))
    .option('--path <subpath>', t('commands.storage.browse.pathOption'), '')
    .action(async (name: string, options: { path: string }) => {
      try {
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
    .command('prune <storageName>')
    .summary(t('commands.storage.prune.descriptionShort'))
    .description(t('commands.storage.prune.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('--dry-run', t('options.dryRun'))
    .option('--force', t('options.force'))
    .option('--grace-days <days>', t('options.graceDays'), Number.parseInt)
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (storageName: string, options: StoragePruneOptions) => {
      try {
        await executeStoragePrune(storageName, options);
      } catch (error) {
        handleError(error);
      }
    });
}
