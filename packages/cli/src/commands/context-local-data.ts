import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { DEFAULTS } from '@rediacc/shared/config';
import { validateNetworkId } from '@rediacc/shared/queue-vault';
import { t } from '../i18n/index.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import type { OutputFormat, RepositoryConfig } from '../types/index.js';
import type { Command } from 'commander';

export function registerLocalDataCommands(context: Command, program: Command): void {
  // context import-storage - Import storages from rclone config file
  context
    .command('import-storage <file>')
    .description(t('commands.context.importStorage.description'))
    .option('--name <name>', t('commands.context.importStorage.optionName'))
    .action(async (file, options) => {
      try {
        const { parseRcloneConfig, mapRcloneToStorageProvider, PROVIDER_MAPPING } = await import(
          '@rediacc/shared/queue-vault'
        );

        const filePath = file.startsWith('~') ? path.join(os.homedir(), file.slice(1)) : file;

        const content = await fs.readFile(filePath, 'utf-8');
        const configs = parseRcloneConfig(content);

        if (configs.length === 0) {
          throw new Error(t('commands.context.importStorage.noConfigs'));
        }

        const toImport = options.name
          ? configs.filter((c: { name: string }) => c.name === options.name)
          : configs;

        if (toImport.length === 0) {
          throw new Error(
            t('commands.context.importStorage.notFound', {
              name: options.name,
            })
          );
        }

        let imported = 0;
        for (const config of toImport) {
          const mapped = mapRcloneToStorageProvider(config);
          if (!mapped) {
            outputService.warn(
              t('commands.context.importStorage.unsupported', {
                name: config.name,
                type: config.type,
              })
            );
            continue;
          }

          await contextService.addLocalStorage(config.name, {
            provider: PROVIDER_MAPPING[config.type] ?? (mapped.provider as string),
            vaultContent: mapped,
          });
          outputService.success(
            t('commands.context.importStorage.imported', {
              name: config.name,
              type: config.type,
            })
          );
          imported++;
        }

        outputService.info(t('commands.context.importStorage.summary', { count: imported }));
      } catch (error) {
        handleError(error);
      }
    });

  // context remove-storage - Remove a storage from local context
  context
    .command('remove-storage <name>')
    .description(t('commands.context.removeStorage.description'))
    .action(async (name) => {
      try {
        await contextService.removeLocalStorage(name);
        outputService.success(t('commands.context.removeStorage.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // context storages - List storages in local context
  context
    .command('storages')
    .description(t('commands.context.storages.description'))
    .action(async () => {
      try {
        const storages = await contextService.listLocalStorages();
        const format = program.opts().output as OutputFormat;

        if (storages.length === 0) {
          outputService.info(t('commands.context.storages.noStorages'));
          return;
        }

        const displayData = storages.map((s) => ({
          name: s.name,
          provider: s.config.provider,
        }));

        outputService.print(displayData, format);
      } catch (error) {
        handleError(error);
      }
    });

  // context add-repository - Add a repository GUID mapping
  context
    .command('add-repository <name>')
    .description(t('commands.context.addRepository.description'))
    .requiredOption('--guid <guid>', t('commands.context.addRepository.optionGuid'))
    .option('--tag <tag>', t('commands.context.addRepository.optionTag'), DEFAULTS.REPOSITORY.TAG)
    .option('--credential <credential>', t('commands.context.addRepository.optionCredential'))
    .option('--network-id <id>', t('commands.context.addRepository.optionNetworkId'))
    .action(async (name, options) => {
      try {
        let networkId: number | undefined;

        if (options.networkId === undefined) {
          networkId = await contextService.allocateNetworkId();
        } else {
          networkId = Number.parseInt(options.networkId, 10);
          const validation = validateNetworkId(networkId);
          if (!validation.valid) {
            throw new ValidationError(validation.error!);
          }
        }

        const config: RepositoryConfig = {
          repositoryGuid: options.guid,
          tag: options.tag,
          credential: options.credential,
          networkId,
        };

        await contextService.addLocalRepository(name, config);
        outputService.success(
          t('commands.context.addRepository.success', {
            name,
            guid: config.repositoryGuid,
            tag: config.tag ?? DEFAULTS.REPOSITORY.TAG,
          })
        );
        outputService.info(t('commands.context.addRepository.networkIdAssigned', { networkId }));
      } catch (error) {
        handleError(error);
      }
    });

  // context remove-repository - Remove a repository mapping
  context
    .command('remove-repository <name>')
    .description(t('commands.context.removeRepository.description'))
    .action(async (name) => {
      try {
        await contextService.removeLocalRepository(name);
        outputService.success(t('commands.context.removeRepository.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // context repositories - List repository mappings
  context
    .command('repositories')
    .description(t('commands.context.repositories.description'))
    .action(async () => {
      try {
        const repos = await contextService.listLocalRepositories();
        const format = program.opts().output as OutputFormat;

        if (repos.length === 0) {
          outputService.info(t('commands.context.repositories.noRepositories'));
          return;
        }

        const displayData = repos.map((r) => ({
          name: r.name,
          guid: r.config.repositoryGuid,
          tag: r.config.tag ?? DEFAULTS.REPOSITORY.TAG,
          credential: r.config.credential ? 'set' : '-',
          networkId: r.config.networkId ?? '-',
        }));

        outputService.print(displayData, format);
      } catch (error) {
        handleError(error);
      }
    });
}
