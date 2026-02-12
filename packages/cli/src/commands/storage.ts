import { Command } from 'commander';
import {
  formatSizeBytes,
  resolveGuidFileNames,
  type RemoteFile,
} from '@rediacc/shared/queue-vault';
import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { contextService } from '../services/context.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { storageBrowserService } from '../services/storage-browser.js';
import { createResourceCommands } from '../utils/commandFactory.js';
import { handleError } from '../utils/errors.js';
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
        const storageConfig = await contextService.getLocalStorage(name);
        const guidMap = await contextService.getRepositoryGuidMap();

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

  // Add pull subcommand for pulling a backup from cloud storage to a machine
  storage
    .command('pull <storageName>')
    .description(t('commands.storage.pull.description'))
    .requiredOption('-r, --repository <name>', t('commands.storage.pull.repositoryOption'))
    .requiredOption('-m, --machine <name>', t('commands.storage.pull.machineOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        storageName: string,
        options: { repository: string; machine: string; debug?: boolean }
      ) => {
        try {
          // Validate storage exists in context
          await contextService.getLocalStorage(storageName);

          // Validate repository exists and warn if no credential
          const repo = await contextService.getLocalRepository(options.repository);
          if (!repo) {
            throw new Error(`Repository "${options.repository}" not found in context`);
          }
          if (!repo.credential) {
            outputService.warn(
              t('commands.storage.pull.noCredential', {
                name: options.repository,
              })
            );
          }

          outputService.info(
            t('commands.storage.pull.starting', {
              repository: options.repository,
              storage: storageName,
              machine: options.machine,
            })
          );

          const result = await localExecutorService.execute({
            functionName: 'backup_pull',
            machineName: options.machine,
            params: {
              sourceType: 'storage',
              from: storageName,
              repository: options.repository,
            },
            debug: options.debug,
          });

          if (result.success) {
            outputService.success(
              t('commands.storage.pull.completed', {
                duration: result.durationMs,
              })
            );
          } else {
            outputService.error(t('commands.storage.pull.failed', { error: result.error }));
            process.exitCode = result.exitCode;
          }
        } catch (error) {
          handleError(error);
        }
      }
    );
}
