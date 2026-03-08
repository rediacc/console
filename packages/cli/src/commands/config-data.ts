import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { DEFAULTS } from '@rediacc/shared/config';
import { validateNetworkId } from '@rediacc/shared/queue-vault';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import type { OutputFormat, RepositoryConfig } from '../types/index.js';
import { handleError, ValidationError } from '../utils/errors.js';

export function registerLocalDataCommands(config: Command, program: Command): void {
  // config import-storage
  config
    .command('import-storage <file>')
    .description(t('commands.config.importStorage.description'))
    .option('--name <name>', t('commands.config.importStorage.optionName'))
    .action(async (file, options) => {
      try {
        const { parseRcloneConfig, mapRcloneToStorageProvider, PROVIDER_MAPPING } = await import(
          '@rediacc/shared/queue-vault'
        );

        const filePath = file.startsWith('~') ? path.join(os.homedir(), file.slice(1)) : file;

        const content = await fs.readFile(filePath, 'utf-8');
        const configs = parseRcloneConfig(content);

        if (configs.length === 0) {
          throw new Error(t('commands.config.importStorage.noConfigs'));
        }

        const toImport = options.name
          ? configs.filter((c: { name: string }) => c.name === options.name)
          : configs;

        if (toImport.length === 0) {
          throw new Error(
            t('commands.config.importStorage.notFound', {
              name: options.name,
            })
          );
        }

        let imported = 0;
        for (const cfg of toImport) {
          const mapped = mapRcloneToStorageProvider(cfg);
          if (!mapped) {
            outputService.warn(
              t('commands.config.importStorage.unsupported', {
                name: cfg.name,
                type: cfg.type,
              })
            );
            continue;
          }

          await configService.addStorage(cfg.name, {
            provider: PROVIDER_MAPPING[cfg.type] ?? (mapped.provider as string),
            vaultContent: mapped,
          });
          outputService.success(
            t('commands.config.importStorage.imported', {
              name: cfg.name,
              type: cfg.type,
            })
          );
          imported++;
        }

        outputService.info(t('commands.config.importStorage.summary', { count: imported }));
      } catch (error) {
        handleError(error);
      }
    });

  // config remove-storage
  config
    .command('remove-storage <name>')
    .description(t('commands.config.removeStorage.description'))
    .action(async (name) => {
      try {
        await configService.removeStorage(name);
        outputService.success(t('commands.config.removeStorage.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // config storages
  config
    .command('storages')
    .description(t('commands.config.storages.description'))
    .action(async () => {
      try {
        const storages = await configService.listStorages();
        const format = program.opts().output as OutputFormat;

        if (storages.length === 0) {
          outputService.info(t('commands.config.storages.noStorages'));
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

  // config add-repository
  config
    .command('add-repository <name>')
    .description(t('commands.config.addRepository.description'))
    .requiredOption('--guid <guid>', t('commands.config.addRepository.optionGuid'))
    .option('--tag <tag>', t('commands.config.addRepository.optionTag'), DEFAULTS.REPOSITORY.TAG)
    .option('--credential <credential>', t('commands.config.addRepository.optionCredential'))
    .option('--network-id <id>', t('commands.config.addRepository.optionNetworkId'))
    .action(async (name, options) => {
      try {
        let networkId: number | undefined;

        if (options.networkId === undefined) {
          networkId = await configService.allocateNetworkId();
        } else {
          networkId = Number.parseInt(options.networkId, 10);
          const validation = validateNetworkId(networkId);
          if (!validation.valid) {
            throw new ValidationError(validation.error!);
          }
        }

        const repoConfig: RepositoryConfig = {
          repositoryGuid: options.guid,
          tag: options.tag,
          credential: options.credential,
          networkId,
        };

        await configService.addRepository(name, repoConfig);
        outputService.success(
          t('commands.config.addRepository.success', {
            name,
            guid: repoConfig.repositoryGuid,
            tag: repoConfig.tag ?? DEFAULTS.REPOSITORY.TAG,
          })
        );
        outputService.info(t('commands.config.addRepository.networkIdAssigned', { networkId }));
      } catch (error) {
        handleError(error);
      }
    });

  // config remove-repository
  config
    .command('remove-repository <name>')
    .description(t('commands.config.removeRepository.description'))
    .action(async (name) => {
      try {
        await configService.removeRepository(name);
        outputService.success(t('commands.config.removeRepository.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // config repositories
  config
    .command('repositories')
    .description(t('commands.config.repositories.description'))
    .action(async () => {
      try {
        const repos = await configService.listRepositories();
        const format = program.opts().output as OutputFormat;

        if (repos.length === 0) {
          outputService.info(t('commands.config.repositories.noRepositories'));
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

  // config list-archived
  config
    .command('list-archived')
    .description(t('commands.config.listArchived.description'))
    .action(async () => {
      try {
        const archived = await configService.listArchivedRepositories();
        const format = program.opts().output as OutputFormat;

        if (archived.length === 0) {
          outputService.info(t('commands.config.listArchived.noArchived'));
          return;
        }

        const displayData = archived.map((r) => ({
          name: r.name,
          guid: r.repositoryGuid,
          credential: r.credential ? 'set' : '-',
          networkId: r.networkId ?? '-',
          deletedAt: r.deletedAt,
        }));

        outputService.print(displayData, format);
      } catch (error) {
        handleError(error);
      }
    });

  // config restore-archived <guid>
  config
    .command('restore-archived <guid>')
    .description(t('commands.config.restoreArchived.description'))
    .option('--name <name>', t('commands.config.restoreArchived.optionName'))
    .action(async (guid, options) => {
      try {
        const restoredName = await configService.restoreArchivedRepository(guid, options.name);
        outputService.success(
          t('commands.config.restoreArchived.success', { name: restoredName, guid })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // config purge-archived
  config
    .command('purge-archived')
    .description(t('commands.config.purgeArchived.description'))
    .action(async () => {
      try {
        const count = await configService.purgeArchivedRepositories();
        if (count === 0) {
          outputService.info(t('commands.config.purgeArchived.noArchived'));
        } else {
          outputService.success(t('commands.config.purgeArchived.success', { count }));
        }
      } catch (error) {
        handleError(error);
      }
    });
}
