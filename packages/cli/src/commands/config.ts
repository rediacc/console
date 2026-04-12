import { DEFAULTS } from '@rediacc/shared/config';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import type { BackupStrategyConfig, OutputFormat, RdcConfig } from '../types/index.js';
import { hasCloudCredentials } from '../types/index.js';
import {
  assertStorageExists,
  BackupDestinationSchema,
  parseConfig,
} from '../utils/config-schema.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { registerRepositoryCommands, registerStorageCommands } from './config-data.js';
import { registerInfraCommands } from './config-infra.js';
import { registerMachineCommands, registerProviderCommands } from './config-setup.js';
import { registerRemoteCommands } from './config-remote.js';
import { registerSSHCommands } from './config-ssh.js';

/** Resolve enabled state from --enable/--disable flags. */
function resolveEnabledFlag(enable?: boolean, disable?: boolean): boolean | undefined {
  if (enable) return true;
  if (disable) return false;
  return undefined;
}

/**
 * Apply backup-strategy set options.
 * --name is always required (strategy name).
 * Without --destination: sets strategy-level fields (schedule, mode, bwlimit, include/exclude).
 * With --destination: upserts a destination within the strategy.
 */
async function applyBackupStrategyOptions(options: {
  name: string;
  destination?: string;
  storage?: string;
  cron?: string;
  mode?: string;
  bwlimit?: string;
  include?: string;
  exclude?: string;
  enable?: boolean;
  disable?: boolean;
}): Promise<void> {
  const enabled = resolveEnabledFlag(options.enable, options.disable);

  if (options.destination) {
    // Destination-level: upsert a destination within the named strategy
    const existing = await configService.getBackupStrategy(options.name);
    const existingDest = existing?.destinations.find((d) => d.name === options.destination);
    const storageName = options.storage ?? existingDest?.storage;
    if (!storageName) {
      throw new ValidationError(
        `--storage is required when creating a new destination. Use: --storage <storage-name>`
      );
    }
    await assertStorageExists(storageName);
    const dest = parseConfig(
      BackupDestinationSchema,
      { name: options.destination, storage: storageName, enabled, bandwidthLimit: options.bwlimit },
      'backup destination'
    );
    await configService.addBackupDestination(options.name, dest);
  } else {
    // Strategy-level: set globals (schedule, mode, bwlimit, include/exclude)
    const update: Partial<BackupStrategyConfig> = {};
    if (options.cron !== undefined) update.schedule = options.cron;
    if (options.mode !== undefined) update.mode = options.mode as 'hot' | 'cold';
    if (enabled !== undefined) update.enabled = enabled;
    if (options.bwlimit !== undefined) update.bandwidthLimit = options.bwlimit;
    if (options.include !== undefined) {
      update.include = options.include.split(',').map((s) => s.trim());
      update.exclude = undefined; // clear exclude when setting include
    }
    if (options.exclude !== undefined) {
      update.exclude = options.exclude.split(',').map((s) => s.trim());
      update.include = undefined; // clear include when setting exclude
    }
    await configService.setBackupStrategy(options.name, update);
  }
}

/** Display a single backup strategy. */
function displayStrategy(name: string, strategy: BackupStrategyConfig): void {
  const mode = strategy.mode ?? 'hot';
  outputService.info(`Strategy: ${name}`);
  outputService.info(`  Schedule: ${strategy.schedule}`);
  outputService.info(`  Mode: ${mode}`);
  outputService.info(`  Enabled: ${strategy.enabled !== false}`);
  if (strategy.bandwidthLimit) {
    outputService.info(`  Bandwidth limit: ${strategy.bandwidthLimit}`);
  }
  if (strategy.include) {
    outputService.info(`  Include: ${strategy.include.join(', ')}`);
  }
  if (strategy.exclude) {
    outputService.info(`  Exclude: ${strategy.exclude.join(', ')}`);
  }
  if (strategy.destinations.length === 0) {
    outputService.info('  Destinations: (none)');
  } else {
    outputService.info('  Destinations:');
    for (const dest of strategy.destinations) {
      const bwlimit = dest.bandwidthLimit ?? strategy.bandwidthLimit ?? '-';
      const enabled = dest.enabled !== false;
      outputService.info(
        `    ${dest.name}  storage=${dest.storage}  bwlimit=${bwlimit}  enabled=${enabled}`
      );
    }
  }
}

/** Build display data for a self-hosted config. */
async function buildSelfHostedDisplay(
  config: RdcConfig,
  name: string
): Promise<Record<string, unknown>> {
  let machineCount = 0;
  let storageCount = 0;
  let repoCount = 0;
  try {
    const state = await configService.getResourceState();
    machineCount = Object.keys(state.getMachines()).length;
    storageCount = Object.keys(state.getStorages()).length;
    repoCount = Object.keys(state.getRepositories()).length;
  } catch {
    machineCount = Object.keys(config.machines ?? {}).length;
    storageCount = Object.keys(config.storages ?? {}).length;
    repoCount = Object.keys(config.repositories ?? {}).length;
  }

  const display: Record<string, unknown> = {
    name,
    id: config.id,
    version: config.version,
    adapter: 'local',
    encrypted: config.encrypted ? 'yes' : 'no',
    sshKey: config.ssh?.privateKeyPath ?? '-',
    renetPath: config.renetPath ?? DEFAULTS.CONTEXT.RENET_PATH,
    machines: machineCount,
    storages: storageCount,
    repositories: repoCount,
  };
  if (config.remote) {
    display.remoteUrl = config.remote.apiUrl;
    display.dataRegion = config.remote.dataRegion ?? '-';
  }
  return display;
}

/** Encrypt master password if provided. Returns config updates. */
async function handleMasterPasswordSetup(options: {
  masterPassword?: string;
}): Promise<Partial<RdcConfig>> {
  if (!options.masterPassword) return {};
  const { nodeCryptoProvider } = await import('../adapters/crypto.js');
  const encrypted = await nodeCryptoProvider.encrypt(
    options.masterPassword,
    options.masterPassword
  );
  return { masterPassword: encrypted, encrypted: true };
}

/** Normalize API URL if provided. Returns config updates. */
async function handleApiUrlSetup(options: { apiUrl?: string }): Promise<Partial<RdcConfig>> {
  if (!options.apiUrl) return {};
  const { apiClient } = await import('../services/api.js');
  return { apiUrl: apiClient.normalizeApiUrl(options.apiUrl) };
}

/** Check whether the user passed any config-init flags beyond --name. */
function hasInitFlags(options: {
  sshKey?: string;
  renetPath?: string;
  masterPassword?: string;
  apiUrl?: string;
  server?: string;
}): boolean {
  return !!(
    options.sshKey ??
    options.renetPath ??
    options.masterPassword ??
    options.apiUrl ??
    options.server
  );
}

export function registerConfigCommands(program: Command): void {
  const config = program
    .command('config')
    .summary(t('commands.config.descriptionShort'))
    .description(t('commands.config.description'));

  config.addHelpText(
    'after',
    `
${t('help.examples')}
  $ rdc config init --name production --ssh-key ~/.ssh/id_ed25519   ${t('help.config.init')}
  $ rdc config machine add --name server-1 --ip 10.0.0.1 --user deploy  ${t('help.config.addMachine')}
  $ rdc config machine setup --name server-1                        ${t('help.config.setupMachine')}
`
  );

  // config init - Initialize a new config file
  config
    .command('init')
    .description(t('commands.config.init.description'))
    .option('--name <name>', t('options.name'))
    .option('--ssh-key <path>', t('options.sshKey'))
    .option('--renet-path <path>', t('options.renetPath'))
    .option('--master-password <password>', t('commands.config.init.optionMasterPassword'))
    .option('-u, --api-url <url>', t('options.apiUrl'))
    .option('--server <url>', t('options.serverUrl'))
    .action(async (options) => {
      try {
        const name = options.name;
        const configName = name ?? DEFAULTS.CONTEXT.CONFIG_NAME;

        const { configFileStorage } = await import('../adapters/config-file-storage.js');
        const exists = await configFileStorage.exists(configName);

        // Named configs must not already exist
        if (exists && name) {
          throw new ValidationError(t('commands.config.init.alreadyExists', { name: configName }));
        }

        // Default config already exists — if no flags, just confirm
        if (exists && !name && !hasInitFlags(options)) {
          outputService.success(t('commands.config.init.success', { name: configName }));
          return;
        }

        const newConfig = exists
          ? await configFileStorage.load(configName)
          : await configService.init(configName);

        const updates: Partial<RdcConfig> = {};

        if (options.sshKey) {
          updates.ssh = { privateKeyPath: options.sshKey };
        }

        if (options.renetPath) {
          updates.renetPath = options.renetPath;
        }

        if (options.server) {
          updates.accountServer = options.server.replace(/\/+$/, '');
        }

        Object.assign(updates, await handleMasterPasswordSetup(options));
        Object.assign(updates, await handleApiUrlSetup(options));
        await configFileStorage.save({ ...newConfig, ...updates }, configName);
        outputService.success(t('commands.config.init.success', { name: configName }));
      } catch (error) {
        handleError(error);
      }
    });

  // config list
  config
    .command('list')
    .alias('ls')
    .description(t('commands.config.list.description'))
    .action(async () => {
      try {
        const configs = await configService.list();
        const format = program.opts().output as OutputFormat;
        const currentName = configService.getCurrentName();

        if (configs.length === 0) {
          outputService.info(t('commands.config.list.noConfigs'));
          return;
        }

        const { configFileStorage } = await import('../adapters/config-file-storage.js');
        const displayData = [];
        for (const name of configs) {
          const cfg = await configFileStorage.load(name);
          const isCloud = hasCloudCredentials(cfg);
          displayData.push({
            name,
            active: name === currentName ? '*' : '',
            adapter: isCloud ? 'cloud' : 'local',
            machines: isCloud ? '-' : Object.keys(cfg.machines ?? {}).length.toString(),
          });
        }

        outputService.print(displayData, format);
      } catch (error) {
        handleError(error);
      }
    });

  // config show
  config
    .command('show')
    .description(t('commands.config.show.description'))
    .action(async () => {
      try {
        const cfg = await configService.getCurrent();
        const format = program.opts().output as OutputFormat;
        const name = configService.getCurrentName();

        if (!cfg) {
          outputService.info(t('commands.config.show.noConfig', { name }));
          return;
        }

        const isCloud = hasCloudCredentials(cfg);
        const display: Record<string, unknown> = isCloud
          ? {
              name,
              id: cfg.id,
              version: cfg.version,
              adapter: 'cloud',
              apiUrl: cfg.apiUrl,
              userEmail: cfg.userEmail ?? '-',
              team: cfg.team ?? '-',
              region: cfg.region ?? '-',
              bridge: cfg.bridge ?? '-',
              authenticated: cfg.token ? 'yes' : 'no',
            }
          : await buildSelfHostedDisplay(cfg, name);

        outputService.print(display, format);
      } catch (error) {
        handleError(error);
      }
    });

  // config delete
  config
    .command('delete')
    .alias('rm')
    .description(t('commands.config.delete.description'))
    .requiredOption('--name <name>', t('options.name'))
    .action(async (options) => {
      try {
        const name = options.name;
        await configService.delete(name);
        outputService.success(t('commands.config.delete.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // config set
  config
    .command('set')
    .description(t('commands.config.set.description'))
    .requiredOption('--key <key>', t('options.configKey'))
    .requiredOption('--value <value>', t('options.configValue'))
    .action(async (options) => {
      try {
        const { key, value } = options;
        const validKeys = ['team', 'region', 'bridge'];
        if (!validKeys.includes(key)) {
          throw new ValidationError(t('errors.invalidKey', { keys: validKeys.join(', ') }));
        }
        await configService.set(key as 'team' | 'region' | 'bridge', value);
        outputService.success(t('commands.config.set.success', { key, value }));
      } catch (error) {
        handleError(error);
      }
    });

  // config clear
  config
    .command('clear')
    .description(t('commands.config.clear.description'))
    .option('--key <key>', t('options.configKey'))
    .action(async (options) => {
      try {
        const key = options.key;
        if (key) {
          const validKeys = ['team', 'region', 'bridge'];
          if (!validKeys.includes(key)) {
            throw new ValidationError(t('errors.invalidKey', { keys: validKeys.join(', ') }));
          }
          await configService.remove(key as 'team' | 'region' | 'bridge');
          outputService.success(t('commands.config.clear.keyCleared', { key }));
        } else {
          await configService.clearDefaults();
          outputService.success(t('commands.config.clear.allCleared'));
        }
      } catch (error) {
        handleError(error);
      }
    });

  // config recover
  config
    .command('recover')
    .description(t('commands.config.recover.description'))
    .option('--name <name>', t('options.name'))
    .option('-y, --yes', t('options.yes'))
    .action(async (options) => {
      try {
        const { configFileStorage } = await import('../adapters/config-file-storage.js');
        const configName = options.name ?? configService.getCurrentName();

        const backupInfo = await configFileStorage.getBackupInfo(configName);
        if (!backupInfo) {
          outputService.info(t('commands.config.recover.noBackup', { name: configName }));
          return;
        }

        const format = program.opts().output as OutputFormat;
        outputService.print(
          {
            config: configName,
            backupVersion: backupInfo.version,
            backupId: backupInfo.id,
            backupDate: backupInfo.modifiedAt.toISOString(),
            backupPath: backupInfo.path,
          },
          format
        );

        if (!options.yes) {
          const { askConfirm } = await import('../utils/prompt.js');
          const confirmed = await askConfirm(
            t('commands.config.recover.confirm', { name: configName })
          );
          if (!confirmed) {
            outputService.info(t('prompts.cancelled'));
            return;
          }
        }

        const recovered = await configFileStorage.recover(configName);
        if (!recovered) {
          outputService.error(t('commands.config.recover.failed', { name: configName }));
          return;
        }

        outputService.success(
          t('commands.config.recover.success', {
            name: configName,
            version: String(recovered.version),
          })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // ── backup-strategy ────────────────────────────────────────────────
  const backupStrategy = config
    .command('backup-strategy')
    .description(t('commands.config.backupStrategy.description'));

  // backup-strategy set
  backupStrategy
    .command('set')
    .description(t('commands.config.backupStrategy.set.description'))
    .requiredOption('--name <name>', t('commands.config.backupStrategy.set.optionName'))
    .option('--destination <name>', t('commands.config.backupStrategy.set.optionDestination'))
    .option('--storage <name>', t('commands.config.backupStrategy.set.optionStorage'))
    .option('--cron <expression>', t('commands.config.backupStrategy.set.optionCron'))
    .option('--mode <mode>', t('commands.config.backupStrategy.set.optionMode'))
    .option('--bwlimit <limit>', t('commands.config.backupStrategy.set.optionBwlimit'))
    .option('--include <repos>', t('commands.config.backupStrategy.set.optionInclude'))
    .option('--exclude <repos>', t('commands.config.backupStrategy.set.optionExclude'))
    .option('--enable', t('commands.config.backupStrategy.set.optionEnable'))
    .option('--disable', t('commands.config.backupStrategy.set.optionDisable'))
    .action(async (options) => {
      try {
        await applyBackupStrategyOptions(options);
        outputService.success(t('commands.config.backupStrategy.set.saved'));
      } catch (error) {
        handleError(error);
      }
    });

  // backup-strategy remove
  backupStrategy
    .command('remove')
    .description(t('commands.config.backupStrategy.remove.description'))
    .requiredOption('--name <name>', t('commands.config.backupStrategy.remove.optionName'))
    .option('--destination <name>', t('commands.config.backupStrategy.remove.optionDestination'))
    .action(async (options) => {
      try {
        if (options.destination) {
          await configService.removeBackupDestination(options.name, options.destination);
        } else {
          await configService.removeBackupStrategy(options.name);
        }
        outputService.success(t('commands.config.backupStrategy.remove.removed'));
      } catch (error) {
        handleError(error);
      }
    });

  // backup-strategy list
  backupStrategy
    .command('list')
    .description(t('commands.config.backupStrategy.list.description'))
    .action(async () => {
      try {
        const strategies = await configService.listBackupStrategies();
        const names = Object.keys(strategies);
        if (names.length === 0) {
          outputService.info(t('commands.config.backupStrategy.show.notConfigured'));
          return;
        }
        for (const name of names) {
          const s = strategies[name];
          const mode = s.mode ?? 'hot';
          const destCount = s.destinations.length;
          const enabled = s.enabled !== false;
          outputService.info(
            `  ${name}  schedule=${s.schedule}  mode=${mode}  destinations=${destCount}  enabled=${enabled}`
          );
        }
      } catch (error) {
        handleError(error);
      }
    });

  // backup-strategy show
  backupStrategy
    .command('show')
    .description(t('commands.config.backupStrategy.show.description'))
    .option('--name <name>', t('commands.config.backupStrategy.show.optionName'))
    .action(async (options) => {
      try {
        if (options.name) {
          const strategy = await configService.getBackupStrategy(options.name);
          if (!strategy) {
            outputService.info(
              t('commands.config.backupStrategy.show.notFound', { name: options.name })
            );
            return;
          }
          displayStrategy(options.name, strategy);
        } else {
          const strategies = await configService.listBackupStrategies();
          const names = Object.keys(strategies);
          if (names.length === 0) {
            outputService.info(t('commands.config.backupStrategy.show.notConfigured'));
            return;
          }
          for (const name of names) {
            displayStrategy(name, strategies[name]);
            outputService.info('');
          }
        }
      } catch (error) {
        handleError(error);
      }
    });

  // Register nested sub-command groups
  registerMachineCommands(config, program);
  registerProviderCommands(config, program);
  registerRepositoryCommands(config, program);
  registerStorageCommands(config, program);
  registerInfraCommands(config, program);
  registerSSHCommands(config, program);
  registerRemoteCommands(config);
}
