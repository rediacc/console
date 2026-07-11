import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { DEFAULTS } from '@rediacc/shared/config';
import { validateNetworkId } from '@rediacc/shared/renet-contract';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import type { OutputFormat } from '../types/index.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { assertResourceName, parseConfig, RepositoryConfigSchema } from '../utils/config-schema.js';
import { handleError, ValidationError } from '../utils/errors.js';

export function registerRepositoryCommands(config: Command, program: Command): void {
  const repository = config
    .command('repository')
    .description(t('commands.config.repository.description'));

  // config repository add
  repository
    .command('add')
    .description(t('commands.config.repository.add.description'))
    .requiredOption('--name <name>', t('options.name'))
    .requiredOption('--guid <guid>', t('commands.config.repository.add.optionGuid'))
    .option('--tag <tag>', t('commands.config.repository.add.optionTag'), DEFAULTS.REPOSITORY.TAG)
    .option('--credential <credential>', t('commands.config.repository.add.optionCredential'))
    .option('--network-id <id>', t('commands.config.repository.add.optionNetworkId'))
    .action(async (options) => {
      try {
        const name = options.name;
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
        );

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
    .command('remove')
    .summary(t('commands.config.repository.remove.descriptionShort'))
    .description(t('commands.config.repository.remove.description'))
    .requiredOption('--name <name>', t('options.name'))
    .action(async (options) => {
      try {
        const { key: target } = await configService.resolveDestructiveTarget(options.name);
        await assertCommandPolicy(CMD.CONFIG_REPOSITORY_REMOVE, target);
        await configService.removeRepository(target);
        outputService.success(t('commands.config.repository.remove.success', { name: target }));
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
          tag: r.tag,
          guid: r.repositoryGuid,
          credential: r.credential ? 'set' : '-',
          deletedAt: r.deletedAt,
        }));

        outputService.print(displayData, format);
      } catch (error) {
        handleError(error);
      }
    });

  // config repository restore-archived
  repository
    .command('restore-archived')
    .description(t('commands.config.repository.restoreArchived.description'))
    .requiredOption('--name <name>', t('options.name'))
    .option('--new-name <name>', t('options.newName'))
    .action(async (options) => {
      try {
        const guid = options.name;
        const restoredName = await configService.restoreArchivedRepository(guid, options.newName);
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

/**
 * Gate `config storage show --reveal`: refuse agents and non-TTY sinks, and
 * audit every grant. Mirrors the reveal gate on `config show` / `config field
 * get` so a storage vault secret is never piped to an agent or a file.
 */
async function applyStorageRevealGate(storageName: string): Promise<void> {
  const { isAgentEnvironment } = await import('../utils/agent-guard.js');
  const { auditLog } = await import('../services/core/audit-log.js');
  const xdg = process.env.XDG_CONFIG_HOME ?? `${process.env.HOME ?? ''}/.config`;
  const auditDir = `${xdg}/rediacc`;
  const pointer = `/resources/storages/${storageName}/vaultContent`;

  if (isAgentEnvironment()) {
    try {
      auditLog(auditDir, {
        command: 'config storage show --reveal',
        paths: [pointer],
        outcome: 'refused',
        reason: 'agent environment',
      });
    } catch {
      /* best-effort */
    }
    throw new ValidationError(t('errors.agent.showReveal'));
  }

  // Use process.stdout.isTTY, not isatty(fd): the fd can be undefined in
  // worker threads or stream wrappers, where isatty() would throw a TypeError.
  if (!process.stdout.isTTY) {
    throw new ValidationError(t('errors.agent.showRevealRequiresTty'));
  }

  try {
    auditLog(auditDir, {
      command: 'config storage show --reveal',
      paths: [pointer],
      outcome: 'reveal_granted',
    });
  } catch {
    /* best-effort */
  }
}

export function registerStorageCommands(config: Command, program: Command): void {
  const storage = config.command('storage').description(t('commands.config.storage.description'));

  // config storage import
  storage
    .command('import')
    .description(t('commands.config.storage.import.description'))
    .requiredOption('--file <path>', t('options.file'))
    .option('--name <name>', t('commands.config.storage.import.optionName'))
    .action(async (options) => {
      try {
        const file = options.file;
        const { parseRcloneConfig, mapRcloneToStorageProvider, PROVIDER_MAPPING } = await import(
          '@rediacc/shared/renet-contract'
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
    .command('remove')
    .description(t('commands.config.storage.remove.description'))
    .requiredOption('--name <name>', t('options.name'))
    .action(async (options) => {
      try {
        const name = options.name;
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

  // config storage show — display one storage's provider + vaultContent.
  // vaultContent is redacted by default (sensitivity map marks it `secret`);
  // --reveal prints it in the clear for a human at an interactive terminal.
  storage
    .command('show')
    .description(t('commands.config.storage.show.description'))
    .requiredOption('--name <name>', t('options.name'))
    .option('--reveal', t('commands.config.storage.show.optionReveal'))
    .action(async (options: { name: string; reveal?: boolean }) => {
      try {
        const storageConfig = await configService.getStorage(options.name);
        const format = program.opts().output as OutputFormat;

        let vaultContent: unknown = storageConfig.vaultContent;
        if (options.reveal) {
          await applyStorageRevealGate(options.name);
        } else {
          const { redactClone } = await import('../schema/walker.js');
          const redacted = redactClone({
            resources: { storages: { [options.name]: storageConfig } },
          }) as { resources: { storages: Record<string, { vaultContent: unknown }> } };
          vaultContent = redacted.resources.storages[options.name].vaultContent;
        }

        outputService.print(
          { name: options.name, provider: storageConfig.provider, vaultContent },
          format
        );
      } catch (error) {
        handleError(error);
      }
    });
}
