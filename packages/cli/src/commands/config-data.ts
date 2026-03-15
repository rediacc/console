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
import { assertResourceName, parseConfig, RepositoryConfigSchema } from '../utils/config-schema.js';
import { handleError, ValidationError } from '../utils/errors.js';

export function registerRepositoryCommands(config: Command, program: Command): void {
  const repository = config
    .command('repository')
    .description(t('commands.config.repository.description'));

  // config repository add
  repository
    .command('add <name>')
    .description(t('commands.config.repository.add.description'))
    .requiredOption('--guid <guid>', t('commands.config.repository.add.optionGuid'))
    .option('--tag <tag>', t('commands.config.repository.add.optionTag'), DEFAULTS.REPOSITORY.TAG)
    .option('--credential <credential>', t('commands.config.repository.add.optionCredential'))
    .option('--network-id <id>', t('commands.config.repository.add.optionNetworkId'))
    .action(async (name, options) => {
      try {
        assertResourceName(name);

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

        const repoConfig = parseConfig(
          RepositoryConfigSchema,
          {
            repositoryGuid: options.guid,
            tag: options.tag,
            credential: options.credential,
            networkId,
          },
          'repository config'
        ) as RepositoryConfig;

        await configService.addRepository(name, repoConfig);
        outputService.success(
          t('commands.config.repository.add.success', {
            name,
            guid: repoConfig.repositoryGuid,
            tag: repoConfig.tag ?? DEFAULTS.REPOSITORY.TAG,
          })
        );
        outputService.info(t('commands.config.repository.add.networkIdAssigned', { networkId }));
      } catch (error) {
        handleError(error);
      }
    });

  // config repository remove
  repository
    .command('remove <name>')
    .description(t('commands.config.repository.remove.description'))
    .action(async (name) => {
      try {
        await configService.removeRepository(name);
        outputService.success(t('commands.config.repository.remove.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // config repository list
  repository
    .command('list')
    .description(t('commands.config.repository.list.description'))
    .action(async () => {
      try {
        const repos = await configService.listRepositories();
        const format = program.opts().output as OutputFormat;

        if (repos.length === 0) {
          outputService.info(t('commands.config.repository.list.noRepositories'));
          return;
        }

        const { parseRepoRef } = await import('../utils/config-schema.js');
        const displayData = repos.map((r) => {
          const { name: baseName, tag: parsedTag } = parseRepoRef(r.name);
          return {
            name: baseName,
            tag: r.config.tag ?? parsedTag,
            type: r.config.grandGuid ? 'fork' : 'grand',
            guid: r.config.repositoryGuid,
            credential: r.config.credential ? 'set' : '-',
            networkId: r.config.networkId ?? '-',
          };
        });

        outputService.print(displayData, format);
      } catch (error) {
        handleError(error);
      }
    });

  // config repository list-archived
  repository
    .command('list-archived')
    .description(t('commands.config.repository.listArchived.description'))
    .action(async () => {
      try {
        const archived = await configService.listArchivedRepositories();
        const format = program.opts().output as OutputFormat;

        if (archived.length === 0) {
          outputService.info(t('commands.config.repository.listArchived.noArchived'));
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

  // config repository restore-archived
  repository
    .command('restore-archived <guid>')
    .description(t('commands.config.repository.restoreArchived.description'))
    .option('--name <name>', t('commands.config.repository.restoreArchived.optionName'))
    .action(async (guid, options) => {
      try {
        const restoredName = await configService.restoreArchivedRepository(guid, options.name);
        outputService.success(
          t('commands.config.repository.restoreArchived.success', { name: restoredName, guid })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // config repository purge-archived
  repository
    .command('purge-archived')
    .description(t('commands.config.repository.purgeArchived.description'))
    .action(async () => {
      try {
        const count = await configService.purgeArchivedRepositories();
        if (count === 0) {
          outputService.info(t('commands.config.repository.purgeArchived.noArchived'));
        } else {
          outputService.success(t('commands.config.repository.purgeArchived.success', { count }));
        }
      } catch (error) {
        handleError(error);
      }
    });
}

export function registerStorageCommands(config: Command, program: Command): void {
  const storage = config.command('storage').description(t('commands.config.storage.description'));

  // config storage import
  storage
    .command('import <file>')
    .description(t('commands.config.storage.import.description'))
    .option('--name <name>', t('commands.config.storage.import.optionName'))
    .action(async (file, options) => {
      try {
        const { parseRcloneConfig, mapRcloneToStorageProvider, PROVIDER_MAPPING } = await import(
          '@rediacc/shared/queue-vault'
        );

        const filePath = file.startsWith('~') ? path.join(os.homedir(), file.slice(1)) : file;

        const content = await fs.readFile(filePath, 'utf-8');
        const configs = parseRcloneConfig(content);

        if (configs.length === 0) {
          throw new Error(t('commands.config.storage.import.noConfigs'));
        }

        const toImport = options.name
          ? configs.filter((c: { name: string }) => c.name === options.name)
          : configs;

        if (toImport.length === 0) {
          throw new Error(
            t('commands.config.storage.import.notFound', {
              name: options.name,
            })
          );
        }

        let imported = 0;
        for (const cfg of toImport) {
          const mapped = mapRcloneToStorageProvider(cfg);
          if (!mapped) {
            outputService.warn(
              t('commands.config.storage.import.unsupported', {
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
            t('commands.config.storage.import.imported', {
              name: cfg.name,
              type: cfg.type,
            })
          );
          imported++;
        }

        outputService.info(t('commands.config.storage.import.summary', { count: imported }));
      } catch (error) {
        handleError(error);
      }
    });

  // config storage remove
  storage
    .command('remove <name>')
    .description(t('commands.config.storage.remove.description'))
    .action(async (name) => {
      try {
        await configService.removeStorage(name);
        outputService.success(t('commands.config.storage.remove.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // config storage list
  storage
    .command('list')
    .description(t('commands.config.storage.list.description'))
    .action(async () => {
      try {
        const storages = await configService.listStorages();
        const format = program.opts().output as OutputFormat;

        if (storages.length === 0) {
          outputService.info(t('commands.config.storage.list.noStorages'));
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
}
