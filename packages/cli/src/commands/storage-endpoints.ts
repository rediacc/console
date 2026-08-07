import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { getStateProvider } from '../services/state.js';
import type { OutputFormat } from '../types/index.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';

/**
 * Gate `storage list <name> --reveal`: refuse agents and non-TTY sinks, and
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
        command: 'storage list --reveal',
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
      command: 'storage list --reveal',
      paths: [pointer],
      outcome: 'reveal_granted',
    });
  } catch {
    /* best-effort */
  }
}

/** `storage add <name>` — register an existing external endpoint. */
function registerAdd(storage: Command): void {
  storage
    .command('add')
    .argument('<name>', t('options.name'))
    .description(t('commands.storage.add.description'))
    .requiredOption('--vault <json>', t('options.vaultJson'))
    .action(async (name: string, options: { vault: string }) => {
      try {
        const provider = getStateProvider();
        await withSpinner(
          t('commands.storage.add.adding', { name }),
          () => provider.storage.create({ storageName: name, vaultContent: options.vault }),
          t('commands.storage.add.added', { name })
        );
      } catch (error) {
        handleError(error);
      }
    });
}

/** `storage remove <name>` — deregister a storage endpoint. */
function registerRemove(storage: Command): void {
  storage
    .command('remove')
    .argument('<name>', t('options.name'))
    .description(t('commands.storage.remove.description'))
    .option('-y, --yes', t('options.yes'))
    .option('--dry-run', t('options.dryRun'))
    .action(async (name: string, options: { yes?: boolean; dryRun?: boolean }) => {
      try {
        if (options.dryRun) {
          outputService.print({ dryRun: true, storage: name }, 'table');
          return;
        }
        if (!options.yes) {
          const { askConfirm } = await import('../utils/prompt.js');
          const confirmed = await askConfirm(t('commands.storage.remove.confirm', { name }));
          if (!confirmed) {
            outputService.info(t('status.cancelled'));
            return;
          }
        }
        const provider = getStateProvider();
        await provider.storage.delete({ storageName: name });
        outputService.success(t('commands.storage.remove.removed', { name }));
      } catch (error) {
        handleError(error);
      }
    });
}

/** `storage list [name]` — list endpoints, or show one in full with --reveal. */
function registerList(storage: Command, program: Command): void {
  storage
    .command('list')
    .argument('[name]', t('options.name'))
    .description(t('commands.storage.list.description'))
    .option('--reveal', t('commands.storage.list.optionReveal'))
    .action(async (name: string | undefined, options: { reveal?: boolean }) => {
      try {
        const format = program.opts().output as OutputFormat;

        if (name) {
          const storageConfig = await configService.getStorage(name);
          let vaultContent: unknown = storageConfig.vaultContent;
          if (options.reveal) {
            await applyStorageRevealGate(name);
          } else {
            const { redactClone } = await import('../schema/fingerprint.js');
            const redacted = redactClone({
              resources: { storages: { [name]: storageConfig } },
            }) as { resources: { storages: Record<string, { vaultContent: unknown }> } };
            vaultContent = redacted.resources.storages[name].vaultContent;
          }
          outputService.print({ name, provider: storageConfig.provider, vaultContent }, format);
          return;
        }

        const storages = await configService.listStorages();
        if (storages.length === 0 && format === 'table') {
          outputService.info(t('commands.storage.list.noStorages'));
          return;
        }
        outputService.print(
          storages.map((s) => ({ name: s.name, provider: s.config.provider })),
          format
        );
      } catch (error) {
        handleError(error);
      }
    });
}

/** `storage import <file>` — import endpoints from an rclone config file. */
function registerImport(storage: Command): void {
  storage
    .command('import')
    .argument('<file>', t('options.file'))
    .description(t('commands.storage.import.description'))
    .option('--name <name>', t('commands.storage.import.optionName'))
    .action(async (file: string, options: { name?: string }) => {
      try {
        const { parseRcloneConfig, mapRcloneToStorageProvider, PROVIDER_MAPPING } = await import(
          '@rediacc/shared/renet-contract'
        );

        const filePath = file.startsWith('~') ? path.join(os.homedir(), file.slice(1)) : file;
        const content = await fs.readFile(filePath, 'utf-8');
        const configs = parseRcloneConfig(content);

        if (configs.length === 0) {
          throw new Error(t('commands.storage.import.noConfigs'));
        }

        const toImport = options.name
          ? configs.filter((c: { name: string }) => c.name === options.name)
          : configs;

        if (toImport.length === 0) {
          throw new Error(t('commands.storage.import.notFound', { name: options.name }));
        }

        let imported = 0;
        for (const cfg of toImport) {
          const mapped = mapRcloneToStorageProvider(cfg);
          if (!mapped) {
            outputService.warn(
              t('commands.storage.import.unsupported', { name: cfg.name, type: cfg.type })
            );
            continue;
          }
          await configService.addStorage(cfg.name, {
            provider: PROVIDER_MAPPING[cfg.type] ?? (mapped.provider as string),
            vaultContent: mapped,
          });
          outputService.success(
            t('commands.storage.import.imported', { name: cfg.name, type: cfg.type })
          );
          imported++;
        }
        outputService.info(t('commands.storage.import.summary', { count: imported }));
      } catch (error) {
        handleError(error);
      }
    });
}

/** Register `storage add/remove/list/import` (endpoint registry). */
export function registerStorageEndpointCommands(storage: Command, program: Command): void {
  registerAdd(storage);
  registerRemove(storage);
  registerList(storage, program);
  registerImport(storage);
}
